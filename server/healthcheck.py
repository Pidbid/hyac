import sys
import http.client


def main():
    """
    Performs a health check by making an HTTP request to the server's health endpoint.
    Exits with 0 on success (HTTP 200), and 1 on failure.
    """
    conn = None
    try:
        # Use http.client to avoid external dependencies like requests or httpx
        conn = http.client.HTTPConnection("localhost", 8000, timeout=10)
        conn.request("GET", "/__server_health__")
        response = conn.getresponse()

        if response.status == 200:
            print("Health check passed.")
            sys.exit(0)
        else:
            print(
                f"Health check failed with status: {response.status}", file=sys.stderr
            )
            print(f"Response: {response.read().decode()}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Health check failed with exception: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
