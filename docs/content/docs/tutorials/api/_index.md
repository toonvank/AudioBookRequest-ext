---
title: API
description: How to use the AudioBookRequest API
---

## Overview

AudioBookRequest provides a RESTful API for a select few endpoints.

The API uses Bearer token authentication with API keys that can be generated
through the web interface.

## How to Create an API Key

Follow these steps to create an API key for accessing the AudioBookRequest API:

1. In the Account settings page, look for the **API Keys** section
2. Enter a unique name for your API key
3. Click on **Create API Key**
4. **Important**: The API key will only be displayed once for security reasons
5. Copy the generated API key immediately and store it in a secure location
6. If you lose the key, you'll need to generate a new one

### Use Your API Key

Include your API key in the Authorization header of your API requests:

```
Authorization: Bearer <your-api-key>
```

**Example using cURL:**

```bash
curl -H "Authorization: Bearer <your-api-key-here>" https://abr.example.com/api/users/me
```

## API Documentation

For a SwaggerUI documentation with interactive testing capabilities:

1. Set the environment variable `ABR_APP__OPENAPI_ENABLED=true`
2. Head to `<your-domain>/docs`.
