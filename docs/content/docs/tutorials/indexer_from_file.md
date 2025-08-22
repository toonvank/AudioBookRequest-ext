---
title: Update indexer configuration from file
description: Update indexer configuration options using a file
---

## Overview

You can set up a JSON file that will be used to populate the indexer
configuration options. This can be useful if you have a value that needs to
constantly change, but you don't want to have to work with the
[ABR API](./api/_index.md).

## How to set up file configuration

1. Create a JSON file with the desired options. The layout is a 2-layer object.
   The top-level is an object with key for each indexer type (for example
   `MyAnonamouse`). The value is an object containing a key for each config that
   you want to update.
2. Ensure the JSON file is visible by ABR. Add it as a volume or copy it into
   the Docker container.
3. Head to `Settings>Indexers`
4. At the bottom, enter the path to the JSON file. It's best to pass in an
   absolute path.
5. You're done! ABR will now check for updates to the file and update the
   configurations if there's ever any change.

## Example

This is an example of a legal JSON file that would update the mam_id.

```json
{
  "MyAnonamouse": {
    "mam_session_id": "test3"
  }
}
```
