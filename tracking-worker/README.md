# Postcode Sector Tracking Worker

This Worker stores aggregate HO.ME postcode-sector search counts in Cloudflare KV.
It does not receive or store full postcodes.

## Deploy

1. Install Wrangler:

   ```sh
   npm install -g wrangler
   ```

2. Log in to Cloudflare:

   ```sh
   wrangler login
   ```

3. Create a KV namespace:

   ```sh
   wrangler kv namespace create POSTCODE_SECTOR_SEARCHES
   ```

4. Copy `wrangler.example.toml` to `wrangler.toml`, then replace the KV namespace
   `id` with the value returned by Wrangler.

5. Optional but recommended: protect the stats endpoint with a read token:

   ```sh
   wrangler secret put READ_TOKEN
   ```

6. Deploy:

   ```sh
   wrangler deploy
   ```

7. Copy the deployed Worker URL into `docs/tracking-config.js`:

   ```js
   window.HOME_POSTCODE_TRACKING_ENDPOINT = 'https://your-worker.your-subdomain.workers.dev';
   ```

8. If you set `READ_TOKEN`, either add it to `docs/tracking-config.js` or open the
   stats page with `?token=...`:

   ```text
   https://hometool.uk/postcode-sector-stats.html?token=your-token
   ```

## Expected API

Record a search:

```http
POST /
Content-Type: application/json

{ "sector": "SE1 7" }
```

Read aggregate counts:

```http
GET /?summary=1&token=optional-read-token
```

Response:

```json
{
  "sectors": [
    { "sector": "SE1 7", "count": 12 }
  ]
}
```
