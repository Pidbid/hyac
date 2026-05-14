# Core Concepts

To effectively use Hyac, it's important to understand a few core concepts.

## Function as a Service (FaaS)

FaaS is a category of cloud computing services that provides a platform allowing customers to develop, run, and manage application functionalities without the complexity of building and maintaining the infrastructure typically associated with developing and launching an app.

## Application

In Hyac, an Application is a collection of functions, dependencies, and configurations. It's a way to group related functions together and manage them as a single unit.

## Function

A Function is a single Python function that can be executed on the Hyac platform. It's the smallest unit of deployment in Hyac.

## Tenant

Hyac is a multi-tenant platform, which means that multiple users can use the same instance of Hyac without interfering with each other. Each user is a tenant, and their resources (applications, functions, etc.) are isolated from other tenants.
