import asyncio
import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from core.jwt_auth import hash_refresh_token
from routers import users as users_router


class _Field:
    def __eq__(self, other):
        return other


class _User:
    username = _Field()
    find_one = None


class _Limiter:
    def __init__(self, _request):
        pass

    def check_rate_limit(self):
        pass

    def record_failed_attempt(self):
        pass

    def reset_attempts(self):
        pass


class _BarrierUserCollection:
    def __init__(self, authoritative, write_started, resume_write):
        self.authoritative = authoritative
        self.write_started = write_started
        self.resume_write = resume_write
        self.queries = []

    async def update_one(self, query, update):
        self.queries.append(query)
        self.write_started.set()
        await self.resume_write.wait()
        if not self._matches(query):
            return SimpleNamespace(matched_count=0)
        self.authoritative.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1)

    def _matches(self, query):
        for field, expected in query.items():
            actual = self.authoritative.get(field)
            if field == "roles" and not isinstance(expected, list):
                if expected not in (actual or []):
                    return False
            elif actual != expected:
                return False
        return True


class UserSessionCASTests(IsolatedAsyncioTestCase):
    async def test_configured_admin_username_is_immutable(self):
        current_user = SimpleNamespace(
            id="user-1",
            username="operator",
            token_version=4,
            refresh_token_hash="refresh-hash",
        )
        with (
            patch.object(users_router.settings, "DEMO_MODE", False),
            patch.object(users_router.settings, "DEFAULT_ADMIN_USER", "operator"),
            patch.object(
                users_router,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(
                        side_effect=AssertionError("database must not be accessed")
                    )
                ),
            ),
        ):
            result = await asyncio.gather(
                users_router.update_me(
                    users_router.UpdateMeRequest(username="renamed_operator"),
                    current_user,
                ),
                return_exceptions=True,
            )

        self.assertIsInstance(result[0], HTTPException)
        self.assertEqual(result[0].status_code, 403)

    async def test_update_me_cannot_restore_security_state_revoked_concurrently(self):
        write_started = asyncio.Event()
        writer_committed = asyncio.Event()
        authoritative = {
            "_id": "user-1",
            "username": "admin",
            "password": "old-password-hash",
            "token_version": 7,
            "refresh_token_hash": "old-refresh-hash",
            "disabled": False,
            "roles": ["admin"],
        }
        profile_snapshot = self._snapshot(
            authoritative, write_started, writer_committed
        )
        security_writer_snapshot = self._snapshot(
            authoritative, write_started, writer_committed
        )
        self.assertIsNot(profile_snapshot, security_writer_snapshot)

        class TransactionContext:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        class Session(TransactionContext):
            async def start_transaction(self):
                return TransactionContext()

            async def with_transaction(self, callback):
                return await callback(self)

        class CASCollection:
            async def find_one(self, _query, **_kwargs):
                return None

            async def update_one(self, query, update, **_kwargs):
                write_started.set()
                await writer_committed.wait()
                if any(authoritative.get(key) != value for key, value in query.items()):
                    return SimpleNamespace(matched_count=0)
                authoritative.update(update.get("$set", {}))
                authoritative["token_version"] += update.get("$inc", {}).get(
                    "token_version", 0
                )
                return SimpleNamespace(matched_count=1)

        session = Session()
        user_collection = CASCollection()
        membership_query = SimpleNamespace(update=AsyncMock())

        class MembershipModel:
            users = _Field()

            @classmethod
            def find(cls, *_conditions):
                return membership_query

        class HistoryModel:
            updated_by = _Field()

            @classmethod
            def find(cls, *_conditions):
                return membership_query

        async def find_user(*_conditions, **_kwargs):
            return None

        async def security_writer():
            await write_started.wait()
            self.assertEqual(security_writer_snapshot.token_version, 7)
            authoritative.update(
                {
                    "password": "rotated-password-hash",
                    "token_version": 12,
                    "refresh_token_hash": "revocation-fence-hash",
                    "disabled": True,
                    "roles": [],
                }
            )
            writer_committed.set()

        _User.find_one = find_user
        collections = {
            _User: user_collection,
            MembershipModel: SimpleNamespace(update_many=AsyncMock()),
            HistoryModel: SimpleNamespace(update_many=AsyncMock()),
        }
        with (
            patch.object(users_router.settings, "DEMO_MODE", False),
            patch.object(users_router, "User", _User),
            patch.object(users_router, "Application", MembershipModel),
            patch.object(users_router, "FunctionsHistory", HistoryModel),
            patch.object(users_router, "Function", MembershipModel),
            patch.object(
                users_router,
                "mongodb_manager",
                SimpleNamespace(
                    client=SimpleNamespace(start_session=MagicMock(return_value=session)),
                    get_collection=MagicMock(side_effect=collections.__getitem__),
                ),
            ),
        ):
            update_task = asyncio.create_task(
                users_router.update_me(
                    users_router.UpdateMeRequest(username="renamed_admin"),
                    profile_snapshot,
                )
            )
            await asyncio.wait_for(write_started.wait(), timeout=1)
            await security_writer()
            results = await asyncio.gather(
                update_task,
                return_exceptions=True,
            )

        self.assertIsInstance(results[0], HTTPException)
        self.assertEqual(results[0].status_code, 409)
        self.assertEqual(authoritative["username"], "admin")
        self.assertEqual(authoritative["password"], "rotated-password-hash")
        self.assertEqual(authoritative["token_version"], 12)
        self.assertEqual(
            authoritative["refresh_token_hash"], "revocation-fence-hash"
        )
        self.assertTrue(authoritative["disabled"])
        self.assertEqual(authoritative["roles"], [])

    async def test_login_cannot_restore_credentials_revoked_during_authentication(self):
        write_started = asyncio.Event()
        resume_write = asyncio.Event()
        authoritative = {
            "_id": "user-1",
            "username": "admin",
            "password": "old-password-hash",
            "token_version": 7,
            "refresh_token_hash": "previous-refresh-hash",
            "disabled": False,
            "roles": ["admin"],
        }
        snapshot = self._snapshot(authoritative, write_started, resume_write)

        async def find_user(*_conditions):
            return snapshot

        _User.find_one = find_user
        collection = _BarrierUserCollection(
            authoritative, write_started, resume_write
        )
        access_token = MagicMock(return_value="new-access")

        with (
            patch.object(users_router, "User", _User),
            patch.object(users_router, "LoginRateLimiter", _Limiter),
            patch.object(users_router, "verify_captcha", return_value={}),
            patch.object(users_router, "verify_password", return_value=True),
            patch.object(users_router, "password_needs_rehash", return_value=False),
            patch.object(users_router, "create_access_token", access_token),
            patch.object(
                users_router, "create_refresh_token", return_value="new-refresh"
            ),
            patch.object(
                users_router,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(return_value=collection)
                ),
            ),
        ):
            login = asyncio.create_task(
                users_router.login_for_access_token(
                    users_router.LoginRequest(
                        username="admin", password="plaintext", captcha="abcd"
                    ),
                    SimpleNamespace(),
                )
            )
            await asyncio.wait_for(write_started.wait(), timeout=1)
            authoritative.update(
                {
                    "password": "rotated-password-hash",
                    "token_version": 8,
                    "refresh_token_hash": None,
                }
            )
            resume_write.set()
            result = await asyncio.gather(login, return_exceptions=True)

        self.assertIsInstance(result[0], HTTPException)
        self.assertEqual(result[0].status_code, 409)
        self.assertEqual(authoritative["password"], "rotated-password-hash")
        self.assertEqual(authoritative["token_version"], 8)
        self.assertIsNone(authoritative["refresh_token_hash"])
        access_token.assert_not_called()

    async def test_refresh_cannot_restore_session_revoked_during_rotation(self):
        write_started = asyncio.Event()
        resume_write = asyncio.Event()
        old_refresh = "old-refresh"
        authoritative = {
            "_id": "user-1",
            "username": "admin",
            "password": "old-password-hash",
            "token_version": 7,
            "refresh_token_hash": hash_refresh_token(old_refresh),
            "disabled": False,
            "roles": ["admin"],
        }
        snapshot = self._snapshot(authoritative, write_started, resume_write)
        collection = _BarrierUserCollection(
            authoritative, write_started, resume_write
        )
        access_token = MagicMock(return_value="new-access")

        with (
            patch.object(
                users_router,
                "verify_refresh_token_and_get_user",
                return_value=snapshot,
            ),
            patch.object(users_router, "create_access_token", access_token),
            patch.object(
                users_router, "create_refresh_token", return_value="new-refresh"
            ),
            patch.object(
                users_router,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(return_value=collection)
                ),
            ),
        ):
            refresh = asyncio.create_task(
                users_router.refresh_token(
                    users_router.RefreshTokenRequest(refreshToken=old_refresh)
                )
            )
            await asyncio.wait_for(write_started.wait(), timeout=1)
            authoritative.update(
                {
                    "password": "rotated-password-hash",
                    "token_version": 8,
                    "refresh_token_hash": None,
                }
            )
            resume_write.set()
            result = await asyncio.gather(refresh, return_exceptions=True)

        self.assertIsInstance(result[0], HTTPException)
        self.assertEqual(result[0].status_code, 409)
        self.assertEqual(authoritative["token_version"], 8)
        self.assertIsNone(authoritative["refresh_token_hash"])
        access_token.assert_not_called()

    async def test_concurrent_refresh_rotation_allows_only_one_success(self):
        old_refresh = "old-refresh"
        authoritative = {
            "_id": "user-1",
            "username": "admin",
            "password": "password-hash",
            "token_version": 7,
            "refresh_token_hash": hash_refresh_token(old_refresh),
            "disabled": False,
            "roles": ["admin"],
        }
        arrived = 0
        both_arrived = asyncio.Event()

        class ConcurrentCollection:
            async def update_one(_self, query, update):
                nonlocal arrived
                arrived += 1
                if arrived == 2:
                    both_arrived.set()
                await both_arrived.wait()
                for field, expected in query.items():
                    actual = authoritative.get(field)
                    if field == "roles" and not isinstance(expected, list):
                        if expected not in (actual or []):
                            return SimpleNamespace(matched_count=0)
                    elif actual != expected:
                        return SimpleNamespace(matched_count=0)
                authoritative.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)

        snapshots = [
            self._snapshot(authoritative, both_arrived, both_arrived),
            self._snapshot(authoritative, both_arrived, both_arrived),
        ]
        save_arrived = 0

        for snapshot in snapshots:
            async def stale_save(current=snapshot):
                nonlocal save_arrived
                save_arrived += 1
                if save_arrived == 2:
                    both_arrived.set()
                await both_arrived.wait()
                authoritative["refresh_token_hash"] = current.refresh_token_hash

            snapshot.save = stale_save

        with (
            patch.object(
                users_router,
                "verify_refresh_token_and_get_user",
                side_effect=snapshots,
            ),
            patch.object(
                users_router,
                "create_refresh_token",
                side_effect=["new-refresh-1", "new-refresh-2"],
            ),
            patch.object(
                users_router,
                "create_access_token",
                side_effect=["new-access-1", "new-access-2"],
            ),
            patch.object(
                users_router,
                "mongodb_manager",
                SimpleNamespace(
                    get_collection=MagicMock(return_value=ConcurrentCollection())
                ),
            ),
        ):
            results = await asyncio.gather(
                users_router.refresh_token(
                    users_router.RefreshTokenRequest(refreshToken=old_refresh)
                ),
                users_router.refresh_token(
                    users_router.RefreshTokenRequest(refreshToken=old_refresh)
                ),
                return_exceptions=True,
            )

        successes = [result for result in results if isinstance(result, dict)]
        conflicts = [result for result in results if isinstance(result, HTTPException)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].status_code, 409)
        self.assertEqual(
            authoritative["refresh_token_hash"],
            hash_refresh_token(successes[0]["data"]["refreshToken"]),
        )

    @staticmethod
    def _snapshot(authoritative, write_started, resume_write):
        snapshot = SimpleNamespace(
            id=authoritative["_id"],
            username=authoritative["username"],
            password=authoritative["password"],
            token_version=authoritative["token_version"],
            refresh_token_hash=authoritative["refresh_token_hash"],
            disabled=authoritative["disabled"],
            roles=list(authoritative["roles"]),
            update_timestamp=MagicMock(),
        )

        async def stale_save(*_args, **_kwargs):
            write_started.set()
            await resume_write.wait()
            authoritative.update(
                {
                    "username": snapshot.username,
                    "password": snapshot.password,
                    "token_version": snapshot.token_version,
                    "refresh_token_hash": snapshot.refresh_token_hash,
                    "disabled": snapshot.disabled,
                    "roles": list(snapshot.roles),
                }
            )

        snapshot.save = stale_save
        return snapshot
