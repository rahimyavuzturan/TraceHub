---
description: "TraceHub MCP sunucuları için salt-okunur kodlama kuralları"
applyTo: "packages/tracehub-mcp-*/**/*.py"
---

# MCP Sunucusu Kuralları

Bu dosyalar hedef sistemlere (Kubernetes, Elasticsearch, Grafana, WinRM, NetScaler,
Azure DevOps) bağlanan salt-okunur araçları içerir.

## Kesin Yasaklar

- Durum değiştiren fonksiyon **yazma**. İsmi `create_/update_/patch_/delete_/apply_/put_/post_/
  restart_/scale_/exec_/drain_/cordon_/rollout_` ile başlayan fonksiyon olamaz.
- `GET`/`HEAD` dışı HTTP fiili kullanma. Tek istisna ES `_search`/`_count` (allowlist'li).
- Kubernetes `exec`, `attach`, `port-forward` API'lerini kullanma.
- `subprocess`, `os.system`, `shell=True` kullanma. WinRM'de sadece whitelist'li komut şablonu.
- `print()` kullanma — STDIO taşımasında protokolü bozar. `structlog` kullan.

## Zorunluluklar

- Her araç `@mcp.tool()` + `@readonly_tool(category=..., cost=...)` ile işaretlenir.
- İlk parametre `ctx: ToolContext`.
- İlk satır `ctx.policy.assert_allowed(environment=..., ...)`.
- Zaman penceresi ve sonuç limiti parametreleri **zorunlu**, varsayılanları dar.
- Docstring **Türkçe**, ne zaman kullanılacağını ve kullanılmayacağını anlatır.
- Dönüş değeri özetlenmiş metin; `summarize_output()` ile kırp, kırpıldığını belirt.
- Çıktı `redact()` içinden geçer (token, parola, TCKN, kart no, e-posta).
- Her çağrı audit event üretir.

## Test

- Her araç için mocklanmış birim testi yaz. Gerçek sisteme bağlanma.
- Yeni paket eklediysen `tests/test_readonly_invariant.py` listesine dahil olduğunu doğrula.
