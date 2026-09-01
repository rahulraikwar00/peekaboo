# OAuth URL Configuration

## Google Cloud Console

### Authorized JavaScript Origins
| Environment | URL |
|-------------|-----|
| Production | `https://zmyyskcijlqlqotfxhbh.supabase.co` |
| Local | `http://localhost:3000` |

### Authorized Redirect URIs
| Environment | URL |
|-------------|-----|
| Production | `https://zmyyskcijlqlqotfxhbh.supabase.co/auth/v1/callback` |
| Local | `https://zmyyskcijlqlqotfxhbh.supabase.co/auth/v1/callback` |

> **Note:** Google always redirects to Supabase's callback URL. Supabase then forwards to your `redirect_to` URL.

---

## Supabase Dashboard

### Site URL
| Environment | URL |
|-------------|-----|
| Production | `https://peekaboo-477i.onrender.com` |
| Local | `http://localhost:3000` |

### Redirect URLs
| Environment | URL | Purpose |
|-------------|-----|---------|
| Production | `https://peekaboo-477i.onrender.com/auth/oauth/callback` | OAuth callback handler |
| Production | `https://peekaboo-477i.onrender.com/auth/success` | Post-login success page |
| Local | `http://localhost:3000/auth/oauth/callback` | OAuth callback handler |
| Local | `http://localhost:3000/auth/success` | Post-login success page |

---

## Environment Variables

### Local Development (.env)
```bash
PEEKABOO_SERVER_URL=http://localhost:3000
SUPABASE_URL=https://zmyyskcijlqlqotfxhbh.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

### Production (Render/dashboard)
```bash
PEEKABOO_SERVER_URL=https://peekaboo-477i.onrender.com
SUPABASE_URL=https://zmyyskcijlqlqotfxhbh.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

---

## OAuth Flow URL Map

### Local Development
```
1. CLI requests:  GET http://localhost:3000/auth/oauth/start?provider=google
2. Server builds: redirect_to=http://localhost:3000/auth/oauth/callback?state=xxx
3. Supabase URL:  https://zmyyskcijlqlqotfxhbh.supabase.co/auth/v1/authorize?redirect_to=http://localhost:3000/auth/oauth/callback?state=xxx
4. Google redirects to: https://zmyyskcijlqlqotfxhbh.supabase.co/auth/v1/callback?code=xxx
5. Supabase redirects to: http://localhost:3000/auth/oauth/callback?state=xxx&code=xxx
6. Server redirects to: http://localhost:3000/auth/success
```

### Production
```
1. CLI requests:  GET https://peekaboo-477i.onrender.com/auth/oauth/start?provider=google
2. Server builds: redirect_to=https://peekaboo-477i.onrender.com/auth/oauth/callback?state=xxx
3. Supabase URL:  https://zmyyskcijlqlqotfxhbh.supabase.co/auth/v1/authorize?redirect_to=https://peekaboo-477i.onrender.com/auth/oauth/callback?state=xxx
4. Google redirects to: https://zmyyskcijlqlqotfxhbh.supabase.co/auth/v1/callback?code=xxx
5. Supabase redirects to: https://peekaboo-477i.onrender.com/auth/oauth/callback?state=xxx&code=xxx
6. Server redirects to: https://peekaboo-477i.onrender.com/auth/success
```

---

## Quick Checklist

- [ ] Google Authorized JavaScript origins includes your Supabase URL
- [ ] Google Authorized redirect URIs includes `https://zmyyskcijlqlqotfxhbh.supabase.co/auth/v1/callback`
- [ ] Supabase Redirect URLs includes `/auth/oauth/callback` for both local and production
- [ ] Supabase Redirect URLs includes `/auth/success` for both local and production
- [ ] `PEEKABOO_SERVER_URL` env var matches the environment (local vs production)
