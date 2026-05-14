# Your First Function

This guide will walk you through the process of creating and deploying your first function on Hyac.

## 1. About Applications

After starting the Hyac project for the first time, a default application will be created for you automatically. Of course, you can also create new applications to group and manage your functions according to your business needs.

If you need to create a new application:

1.  Navigate to the "Application Management" page.
2.  Click the "New Application" button.
3.  Fill in the required information and click "Create".

## 2. Create a Function

Once you have an application, you can start creating functions.

1.  Navigate to the "Function Management" page.
2.  Click the "New Function" button.
3.  Select an application to house your function.
4.  Fill in the required information, including the function code.
5.  Click "Create".

## 3. Invoking and Testing the Function

After the function is created successfully, you can invoke and test it.

### Function Test Feature

During the development and testing phases, we highly recommend using the "Function Test" feature on the right side of the function details page.

1.  In the function list, click the function you just created to go to its details page.
2.  In the "Function Test" area on the right side of the page, you will see a generated test link.
3.  Copy this link to invoke it directly through a browser or a tool like `curl`.

**Please note:** The "Function Test" feature uses the internal service address of the Docker container network (e.g., `server:8000`), which ensures stability and speed in the development environment. This address format, which utilizes Docker's internal DNS resolution, is only valid within the container network and cannot guarantee reliable access from external networks or via external domain names.

### API Endpoint Invocation

When you are ready to integrate the function into a production environment, you should use the standard API endpoint. The endpoint follows the format `https://<app-id>.<your-domain>/<function-id>`.

You can use a tool like `curl` or Postman to send a request to the endpoint.

```bash
# Example: Using curl to call the API endpoint
# Replace <app-id> with your Application ID
# Replace <your-domain> with your configured domain
# Replace <function-id> with your Function ID
curl -X POST https://<app-id>.<your-domain>/<function-id>
