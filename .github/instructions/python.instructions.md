---
description: "TraceHub Python kodlama standartları"
applyTo: "packages/**/*.py"
---

# Python Kuralları

- Python 3.12+, tam tip anotasyonu, `mypy --strict` geçmeli.
- Veri yapıları `pydantic.BaseModel` veya `dataclass(frozen=True)`.
- I/O `async`. Senkron kütüphane şartsa `asyncio.to_thread`.
- Ayarlar `from tracehub_core.config import settings` üzerinden. `os.environ` doğrudan okunmaz.
- Loglama `structlog`. `print()` yok.
- `except Exception: pass` yok — hatayı işle veya yukarı bırak.
- Kod/yorum/docstring İngilizce; kullanıcıya görünen metin Türkçe ve
  `tracehub_core/messages.py` içinde. (İstisna: MCP araç docstring'leri Türkçe —
  LLM araç seçimi için.)
- Sır loglanmaz, LLM'e gönderilmez.
- SQL parametreli; string birleştirme ile sorgu kurulmaz.
- Gereksiz soyutlama, gereksiz savunmacı kod ve istenmeyen özellik ekleme.
