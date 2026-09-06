# Caddy origin certificates

Place your Cloudflare **Origin Certificate** here:

- `origin.pem` — the Origin Certificate from Cloudflare
  (SSL/TLS -> Origin Server -> Create Certificate)
- `origin.key` — the matching private key

These two files are gitignored (secrets). Create them after generating a
certificate in the Cloudflare dashboard for the hostname
`peekaboo.iamrahulraikwar.online`.

Cloudflare SSL/TLS mode must be set to **Full (Strict)** so Cloudflare
validates that Caddy presents this origin certificate.
