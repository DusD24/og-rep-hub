# Receipt-update Worker

This narrowly scoped Cloudflare Worker accepts anonymous receipt-update requests from the production OG Rep Hub Pages origin. It verifies Turnstile, applies a per-IP Cloudflare rate limit, validates and normalizes allowed public evidence URLs, resolves canonical receipt metadata server-side, and creates a public issue in `DusD24/og-rep-hub`.

## One-time setup

1. Create a Cloudflare Turnstile widget for `dusd24.github.io`. The form and Worker use the action `receipt_update`.
2. Create a repository-scoped GitHub token with Issues write access only.
3. Store runtime secrets directly in Cloudflare; never add them to repository variables or files:

   ```sh
   pnpm exec wrangler secret put GITHUB_ISSUE_TOKEN --config worker/wrangler.jsonc
   pnpm exec wrangler secret put TURNSTILE_SECRET_KEY --config worker/wrangler.jsonc
   ```

4. Add these GitHub Actions repository secrets:

   - `CLOUDFLARE_API_TOKEN`: scoped to deploy this Worker
   - `CLOUDFLARE_ACCOUNT_ID`: the owning Cloudflare account ID

5. Add these GitHub Actions repository variables:

   - `ISSUE_INTAKE_URL`: the deployed Worker HTTPS origin, without the route suffix
   - `TURNSTILE_SITE_KEY`: the public Turnstile site key

6. Keep the repository labels `receipt-update`, `research`, `source-review`, and `bag-collection` provisioned. `source-review` is added to source/media-review requests only.

## Release behavior

Run `pnpm test` and a Wrangler dry run locally. The release workflow deploys the Worker with the Git commit SHA as `BUILD_SHA`, generates the public Pages configuration only inside the Pages artifact, and publishes the same SHA in `build-meta.json`. Pages will not deploy if the Worker deployment fails, and the workflow remains incomplete until both public endpoints report the same SHA.

The Worker allows `POST` and production-origin `OPTIONS` only at `/issues/receipt-update`. `GET /health` reports the deployed build SHA. Secrets stay in Cloudflare; the static site contains only the Worker URL and public Turnstile site key.
