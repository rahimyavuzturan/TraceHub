# TraceHub — Ajan Rehberi (AGENTS.md)

> Bu dosya, bu depoda kod yazan **yapay zeka ajanları** ve geliştiriciler içindir.
> Kod yazmaya başlamadan önce **tamamını** oku. Özellikle "Altın Kural" bölümü pazarlık konusu değildir.

## 0. Nereden Başlamalı

1. Bu dosyayı baştan sona oku.
2. [docs/08-STATUS.md](docs/08-STATUS.md) — projenin güncel durumu, sıradaki görev.
3. [docs/04-WORK-BREAKDOWN.md](docs/04-WORK-BREAKDOWN.md) — göreceğin görevin kabul kriterleri.
4. Görevle ilgili derinlik dokümanı:
   [mimari](docs/02-ARCHITECTURE.md) · [bilgi tabanı](docs/05-KNOWLEDGE-BASE.md) ·
   [güvenlik](docs/06-SECURITY.md) · [kararlar](docs/07-DECISIONS.md)

**Görev bitince [docs/08-STATUS.md](docs/08-STATUS.md)'i güncelle.** Bu zorunludur.

Kapsam dışına çıkma: sana verilen görevin ötesine geçme, istenmeyen özellik ekleme.
Bir karara katılmıyorsan önce [docs/07-DECISIONS.md](docs/07-DECISIONS.md)'deki gerekçeyi oku.

---

## 1. Proje Nedir?

**TraceHub**, bir DevOps ekibine gelen günlük talepleri ("X uygulamasında arıza var", "Y reposunu
silebilir miyiz?") alan; kurum içi bilgi arşivi (RAG) ve **salt-okunur** sistem entegrasyonlarını
kullanarak sorunu kendi kendine araştıran; hiçbir değişiklik yapmadan **kök neden analizi** ve
**adım adım eylem önerisi** sunan bir web uygulamasıdır.

Çalışma modeli:

```
Talep → Normalize → Bilgi tabanı araması → PLAN ÜRET → [KULLANICI ONAYI] →
  Onaylı plan içinde otonom araştırma (salt-okunur araçlar) → Kanıtlı rapor → Vaka hafızası
```

TraceHub **asla** bir sorunu kendi düzeltmez. Kullanıcıya ne yapması gerektiğini,
hangi onayların gerektiğini ve hangi linklere gitmesi gerektiğini söyler.

---

## 2. ALTIN KURAL — Salt Okunur (Read-Only)

Bu projedeki **en önemli** kural budur. İhlali kabul edilemez.

### Yapılmayacaklar (kesin yasak)

- Hedef sistemlerde durum değiştiren **hiçbir** fonksiyon yazılmaz. Yazılmadığı için
  "yanlışlıkla çağrılması" da mümkün olmaz.
- `create_*`, `update_*`, `patch_*`, `delete_*`, `apply_*`, `put_*`, `post_*`, `restart_*`,
  `scale_*`, `exec_*`, `drain_*`, `cordon_*`, `rollout_*` isimli fonksiyonlar MCP paketlerinde
  **bulunamaz**. (Bu, `tests/test_readonly_invariant.py` içindeki AST testi ile zorunlu kılınır.)
- HTTP istemcilerinde `GET` ve `HEAD` dışında fiil kullanılmaz.
  Tek istisna: Elasticsearch `_search` ve `_count` uç noktaları (gövde gerektirdiği için `POST`).
  Bu istisna `tracehub_mcp_common.http.ReadOnlyHttpClient` içinde **açıkça allowlist'lenmiştir**,
  başka yerde `POST` kullanılamaz.
- Kubernetes tarafında `exec`, `attach`, `port-forward`, `portforward` **kullanılmaz**.
- WinRM tarafında serbest komut çalıştırılmaz. Sadece `winrm_commands.yaml` içindeki
  parametreli, whitelist'lenmiş komut şablonları çalıştırılır.

### Üç Katmanlı Savunma

| Katman | Nerede | Ne yapar |
|---|---|---|
| 1. Kimlik | Hedef sistemlerde | k8s `view` ClusterRole, ES read-only role, Grafana Viewer, AzDO read-scope PAT, NetScaler read-only cmdpolicy, WinRM JEA endpoint |
| 2. Kod | `tracehub-mcp-common` | `@readonly_tool` dekoratörü, `ReadOnlyHttpClient` fiil allowlist'i, AST invariant testi |
| 3. Politika | `tracehub-mcp-common/policy.py` | Ortam/namespace/index/host allowlist, prod işaretleme, sorgu bütçesi, redaction, rate limit |

Bir katman yeterli değildir. **Üçünü de** uygula.

---

## 3. Dizin Yapısı

Tam dizin ağacı: [docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) §3. Özet:

```
TraceHub/
├─ AGENTS.md                     # bu dosya
├─ docs/                         # proje planı, mimari, iş kırılımı, güvenlik, durum
├─ pyproject.toml                # uv/pip workspace kökü
├─ docker-compose.yml            # postgres+pgvector (geliştirme)
├─ .env.example                  # tüm ayarların şablonu — GERÇEK SIR ASLA COMMIT EDİLMEZ
├─ packages/
│  ├─ tracehub-core/             # ortak: config, logging, db, llm, embedding, şemalar
│  ├─ tracehub-kb/               # bilgi tabanı: frontmatter, chunker, ingest, hibrit arama
│  ├─ tracehub-api/              # FastAPI uygulaması, SSE, auth, audit
│  ├─ tracehub-agent/            # LangGraph orkestrasyonu (plan/onay/araştırma/rapor)
│  ├─ tracehub-mcp-common/       # MCP ortak katmanı (guard, policy, redaction, http)
│  └─ tracehub-mcp-*/            # tek tek MCP sunucuları (k8s, elastic, grafana, winrm, ...)
├─ knowledge/                    # bilgi tabanı markdown dosyaları (git'te versiyonlu)
│  ├─ service_catalog/
│  ├─ topology/
│  ├─ runbooks/
│  ├─ cases/
│  └─ glossary/
├─ web/                          # React + Vite + TS arayüz
└─ tests/                        # çapraz paket testleri (invariant testleri dahil)
```

---

## 4. Teknoloji Yığını

| Katman | Seçim | Not |
|---|---|---|
| Orkestrasyon | LangGraph | `interrupt()` ile plan-onay kapısı |
| API | FastAPI + SSE | `uvicorn` |
| Paket yönetimi | uv (yoksa pip + venv) | workspace yapısı |
| Kod kalitesi | ruff, mypy (strict), pytest | CI'da zorunlu |
| Veritabanı | PostgreSQL 16 + pgvector | alembic migration |
| LLM | vLLM üzerinde Qwen3-32B-Instruct | OpenAI uyumlu API |
| Embedding | BAAI/bge-m3 (1024 boyut) | çok dilli, Türkçe güçlü |
| Araçlar | Python MCP SDK 2.x | kendi yazdığımız sunucular |
| Arayüz | React 18 + Vite + TS + TanStack Query + Tailwind | **Node 18+ gerekir** |
| Dağıtım | Docker + Helm | Kubernetes |

---

## 5. Kodlama Kuralları

### Dil

- **Kullanıcıya görünen her şey Türkçe**: arayüz metinleri, LLM sistem promptları,
  hata mesajları, rapor çıktıları, bilgi tabanı içeriği.
- **Kodun kendisi İngilizce**: değişken/fonksiyon/sınıf isimleri, docstring, kod yorumu,
  commit mesajı, log mesajı.
- Bu ikisini karıştırma. Türkçe kullanıcı metinlerini kodun içine gömme;
  `tracehub_core/messages.py` veya frontend `i18n` dosyalarında tut.

### Python

- Python 3.12+, her yerde tip anotasyonu. `mypy --strict` geçmeli.
- Veri taşıyan her yapı `pydantic.BaseModel` veya `dataclass(frozen=True)`.
- I/O yapan her şey `async`. Senkron kütüphane şartsa `asyncio.to_thread` kullan.
- Ayarlar sadece `tracehub_core.config.settings` üzerinden okunur;
  `os.environ` koda doğrudan yazılmaz.
- Loglama `structlog` ile yapılır, `print()` kullanılmaz.
  **STDIO MCP sunucularında `print()` protokolü bozar** — kesinlikle yasak.
- Genel `except Exception: pass` yazma. Hatayı ya işle ya da yukarı bırak.

### Güvenlik

- Sır (parola, token, PAT) asla loglanmaz, asla LLM'e gönderilmez.
  Tool çıktıları LLM'e verilmeden önce `redaction.redact()` içinden geçer.
- Kullanıcı girdisi veya LLM çıktısı **hiçbir zaman** shell'e, SQL'e veya
  sorgu diline string birleştirme ile konmaz. Parametreli sorgu kullan.
- Elasticsearch sorgularında zaman penceresi ve `size` limiti **zorunludur**.
- Her araç çağrısı `audit` tablosuna yazılır: kim, ne zaman, hangi ortam, hangi parametre.

### Aşırı mühendislik yapma

- İstenmeyen özellik ekleme, gereksiz soyutlama yazma.
- Tek seferlik işler için yardımcı sınıf üretme.
- Olamayacak senaryolar için savunmacı kod yazma. Sadece sistem sınırlarında doğrula.

---

## 6. MCP Aracı Yazma Şablonu

Yeni bir salt-okunur araç eklerken **bu iskeleti** kullan:

```python
from tracehub_mcp_common import readonly_tool, ToolContext, ToolBudget

@mcp.tool()
@readonly_tool(category="k8s", cost=ToolBudget.CHEAP)
async def pod_logs(
    ctx: ToolContext,
    environment: str,          # "prod" | "preprod" | "test" | "dmz-prod" | ...
    namespace: str,
    pod: str,
    container: str | None = None,
    tail_lines: int = 200,     # üst sınır policy tarafından kısıtlanır
    since_minutes: int = 30,   # zaman penceresi ZORUNLU
) -> str:
    """Bir pod'un günlüklerini getirir (salt okunur).

    Args:
        environment: Hedef ortam adı. Allowlist'te olmalı.
        namespace: Kubernetes namespace'i.
        pod: Pod adı.
        container: Çok kapsayıcılı pod'larda kapsayıcı adı.
        tail_lines: Sondan kaç satır okunacağı.
        since_minutes: Kaç dakika geriye bakılacağı.
    """
    ctx.policy.assert_allowed(environment=environment, namespace=namespace)
    ...
```

Kurallar:

1. Her aracın ilk parametresi `ctx: ToolContext` olmalı.
2. Docstring **Türkçe** ve açıklayıcı olmalı — LLM aracı bu metinden seçer.
   Ne zaman kullanılacağını ve ne zaman kullanılmayacağını yaz.
3. Zaman penceresi / limit parametreleri zorunlu, varsayılanları dar tut.
4. `ctx.policy.assert_allowed(...)` çağrısı **ilk satır** olmalı.
5. Dönüş değeri LLM'in okuyacağı, **özetlenmiş** metin olmalı — ham JSON dökme.
   Büyük çıktıyı `summarize_output()` ile kırp, kırpıldığını belirt.
6. Yeni araç ekledikten sonra `tests/test_readonly_invariant.py` çalıştır.

---

## 7. Komutlar

```powershell
# Geliştirme ortamı
docker compose up -d                       # postgres + pgvector
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Kalite kapıları (commit öncesi hepsini çalıştır)
ruff check .
ruff format --check .
mypy packages
pytest -q

# Veritabanı
alembic upgrade head
alembic revision --autogenerate -m "aciklama"

# Bilgi tabanı
tracehub kb validate                       # frontmatter doğrulaması
tracehub kb ingest                         # knowledge/ -> pgvector
tracehub kb search "mobil prep arizasi"    # hibrit arama testi

# API
uvicorn tracehub_api.main:app --reload --port 8000
```

---

## 8. Test Beklentileri

- Her MCP aracı için en az bir **mocklanmış** birim testi.
- Her yeni MCP paketi `tests/test_readonly_invariant.py` AST taramasından geçmeli.
- Ajan davranışı, kaydedilmiş araç cevaplarıyla **offline replay** edilerek test edilir
  (`tests/golden/`). Gerçek sisteme bağlanan test yazma.
- LLM gerektiren testlerde `MockLLM` kullan; CI'da gerçek model yoktur.

---

## 9. Kapsam Dışı (bilerek yapılmayacaklar)

Otomatik düzeltme/remediation, mail veya ticket sisteminden otomatik talep çekme,
Teams/Slack botu, model fine-tune, LDAP/AD entegrasyonu, RDP ekran görüntüsü analizi.

Bunlardan birini eklemen istenirse önce bu dosyayı güncelle, sonra kodu yaz.

---

## 10. Sık Yapılan Hatalar

| Hata | Doğrusu |
|---|---|
| MCP aracında `print()` ile debug | `structlog` logger kullan (stderr'e yazar) |
| Araç ham JSON döndürüyor | Özetle, kırp, kırpıldığını belirt |
| Zaman penceresiz ES sorgusu | `since_minutes` / `from`-`to` zorunlu |
| Docstring İngilizce | Araç docstring'i Türkçe — LLM seçimini etkiler |
| Ayar `os.getenv` ile okunmuş | `settings` üzerinden oku |
| Tool çıktısı redaction'sız LLM'e gitmiş | `redact()` içinden geçir |
| Yeni ortam eklenmiş ama allowlist güncellenmemiş | `policy.yaml` güncelle |
