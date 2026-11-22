---
id: backend/http-caching/01-freshness
title: Freshness and Cache-Control
level: intro
requires: []
sources:
  - title: "RFC 9111 §4.2 Freshness"
    url: https://www.rfc-editor.org/rfc/rfc9111#name-freshness
  - title: "RFC 9111 §5.2 Cache-Control"
    url: https://www.rfc-editor.org/rfc/rfc9111#name-cache-control
  - title: "MDN: HTTP caching"
    url: https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching
  - title: "MDN: Cache-Control header"
    url: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
updated: 2026-11-21
---

A cache keeps a copy of a response so the next request can be answered without asking the origin again. Every time it uses a copy, it must decide whether the copy is still *fresh*. A fresh copy can be reused directly. A stale copy has to be checked with the origin first, which is the subject of lesson 02.

## Freshness lifetime

The origin says how long a response stays fresh with `Cache-Control: max-age=<seconds>`. The response is fresh while its current age is less than `max-age`. The current age is the time since the origin produced the response, including time it spent in other caches, which those caches report in the `Age` header.

```
HTTP/1.1 200 OK
Cache-Control: max-age=60
Age: 0
```

With `max-age=60`, a copy received 90 seconds ago is stale. The cache must not reuse it without validating it first.

If a response carries no explicit lifetime, caches may guess one from its `Last-Modified` date. Do not rely on that guess. Send `max-age` for anything that must be cached on purpose.

## Three directives that sound alike

- `no-cache` allows the response to be stored, but the cache must revalidate with the origin before every reuse, even while `max-age` has not run out. Pair it with a validator (lesson 02) so the revalidation costs a `304` and no body. `no-cache` does not mean "do not cache".
- `no-store` forbids keeping any copy at all, in memory or on disk. Use it for responses that carry sensitive data.
- `max-age=0` makes the response stale at once, so every reuse goes back to the origin. In effect it is close to `no-cache`, but it states a lifetime and says nothing about storage.

If you want the response kept but never reused unchecked, write `no-cache`. If you want it never kept, write `no-store`.

## Who may store it

`private` lets only the user's own browser cache store the response. This matters for personalised pages. `public` lets shared caches, such as a CDN, store it even when the request carried credentials. Without either, shared caches may store a response only when its headers make that clearly allowed.

## Try it

Run `curl -sI <url>` against any site and read the `Cache-Control` and `Age` headers. Then work out, for each response, how long a cache may reuse it without asking the origin.
