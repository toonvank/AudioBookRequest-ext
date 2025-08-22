---
title: Indexers
description: Using the API to access/update indexers
---

There are two main endpoints to work with indexers:

- A `PATCH` to update indexer settings.
- A `GET` to get all the available configuration settings for the indexers.

Head to the main [API Docs](./_index.md) to see how you can access the SwaggerUI
and more easily test the endpoints.

## Getting the Indexer Configurations

To figure out what values you need to adjust, `GET` the endpoint
`/api/indexers/configurations`.

This will give you something along the lines of this:

```json
{
  "MyAnonamouse": [
    {
      "name": "mam_session_id",
      "description": null,
      "default": null,
      "required": true,
      "type": "str"
    },
    {
      "name": "mam_active",
      "description": null,
      "default": "True",
      "required": false,
      "type": "bool"
    }
  ]
}
```

This gives you the full information about what values can be adjusted.

## Updating Indexer Settings

You can update indexer settings by sending a `PATCH` request to
`/api/indexers/{indexer name}`. The name is **case-sensitive**. The body has to
be a JSON object with key-value pairs of the values you want to update.

Here is an example using cURL: as

```bash
curl -X 'PATCH' \
    'https://abr.example.com/api/indexers/MyAnonamouse' \
    -H 'accept: application/json' \
    -H 'Authorization: Bearer MaEqMYAGY3qvXxtje6-YDxcs4damlyRaKzTC8itG2b8' \
    -d '{"mam_session_id":"bXDv1tC1d2MVvOypbFy8Q4Q-rz6q-bKwdqaSZzm85Dg"}'
```
