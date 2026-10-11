# 08 — Durum

> **Her oturuma buradan başla.** Görev alırken "Devam ediyor" yap, bitirince "Tamam" yap
> ve kısa bir not düş. Bu dosya projenin tek ilerleme kaynağıdır.

**Son güncelleme:** 2026-09-30
**Aktif faz:** Faz 2 — Araçlar (MCP)
**Sıradaki görev:** T2.2 — Kubernetes salt-okunur MCP sunucusu (Docker gerektirmez, mocklu test) · alternatif: T1.2 (⚠️ pgvector için Docker gerekiyor)

---

## Geliştirme Ortamı Durumu

| Araç | Durum | Not |
|---|---|---|
| Python | ✅ 3.12.5 | `.venv` kuruldu, `pip install -e ".[dev]"` başarılı |
| Docker | ⚠️ 25.0.3 | Kurulu ama **daemon çalışmıyor**. T0.3 için Docker Desktop başlatılmalı |
| Git | ✅ 2.49.0 | Uygun |
| uv | ❌ Kurulu değil | pip + venv ile ilerleniyor, sorun yok |
| Node | ⚠️ v16.20.2 | **Vite için 18+ gerekli.** T0.5 öncesi yükseltilmeli (ADR-12) |
| vLLM / GPU | ⬜ Bağlanmadı | `TRACEHUB_LLM__PROVIDER=mock` ile geliştirme yapılabilir |
| PostgreSQL | ⬜ Başlatılmadı | Docker daemon bekliyor |

### Kalite kapıları (son çalıştırma: 2026-09-30)

| Kapı | Sonuç |
|---|---|
| `ruff check .` | ✅ temiz |
| `ruff format --check .` | ✅ temiz |
| `mypy packages` | ✅ 25 dosya, hata yok |
| `pytest -q` | ✅ 180 test geçti |
| `tracehub kb validate` | ✅ 5 doküman, hata yok |

---

## Görev Durumu

Durum kodları: ⬜ Başlanmadı · 🔵 Devam ediyor · ✅ Tamam · ⏸️ Beklemede · ❌ İptal

### Dokümantasyon

| Görev | Durum | Not |
|---|---|---|
| AGENTS.md | ✅ | Altın kural, kodlama standartları, MCP şablonu |
| `.github/instructions/` | ✅ | python + mcp-server kuralları |
| docs/01 — Proje Planı | ✅ | |
| docs/02 — Mimari | ✅ | |
| docs/03 — Teknoloji Yığını | ✅ | |
| docs/04 — İş Kırılımı | ✅ | |
| docs/05 — Bilgi Tabanı | ✅ | |
| docs/06 — Güvenlik | ✅ | |
| docs/07 — Kararlar | ✅ | ADR-01..12 |
| docs/08 — Durum | ✅ | bu dosya |

### Faz 0 — İskelet

| Görev | Durum | Not |
|---|---|---|
| T0.1 Monorepo iskeleti | ✅ | `pyproject.toml` (ruff/mypy/pytest), `docker-compose.yml`, `.env.example`, `.gitignore`, 3 paket iskeleti, `tracehub` CLI. Kurulum ve kapılar doğrulandı |
| T0.2 config + logging + messages | ✅ | Ortam değişkeni geçersiz kılma, `SecretStr` maskeleme, **stderr'e loglama** testleri yazıldı |
| T0.3 DB şeması + migration | 🔵 Kısmen | `db/base.py` hazır; `models.py` ve alembic **yok**. Docker daemon gerekiyor |
| T0.4 LLM + embedding + MockLLM | ✅ | `llm/` paketi: types, base (yapılandırılmış çıktı + 1 onarım turu), openai_compatible (tenacity retry), mock, embedding (hash + HTTP). 36 test |
| T0.5 Arayüz iskeleti | ⏸️ | Node 18+ bekliyor |

### Faz 1 — Bilgi Tabanı

| Görev | Durum |
|---|---|
| T1.1 Şema + doğrulayıcı | ✅ `schema.py` (5 doküman tipi), `loader.py` (satır numaralı Türkçe hatalar), `tracehub kb validate` / `kb list`, 5 örnek doküman. 26 test |
| T1.2 Parçalama + ingest | ⬜ |
| T1.3 Hibrit arama | ⬜ |
| T1.4 KB MCP + arayüz | ⬜ |
| T1.5 Ham metin asistanı | ⬜ |
| T1.6 AzDO Wiki içe aktarım | ⬜ |

### Faz 2 — MCP Temeli

| Görev | Durum |
|---|---|
| T2.1 MCP ortak katmanı | ✅ |
| T2.2 Kubernetes sunucusu | ⬜ |
| T2.3 Elasticsearch sunucusu | ⬜ |
| T2.4 MCP host | ⬜ |

### Faz 3 — Orkestrasyon

| Görev | Durum |
|---|---|
| T3.1 Durum + normalize | ⬜ |
| T3.2 Bilgi getirme | ⬜ |
| T3.3 Plan üretme | ⬜ |
| T3.4 Onay kapısı | ⬜ |
| T3.5 Araştırma döngüsü | ⬜ |
| T3.6 Rapor | ⬜ |
| T3.7 SSE canlı iz | ⬜ |
| T3.8 Audit görüntüleyici | ⬜ |

### Faz 4 — Kabul Senaryosu K1

| Görev | Durum |
|---|---|
| T4.1 Golden test altyapısı | ⬜ |
| T4.2 Prompt iyileştirme | ⬜ |
| T4.3 Vaka hafızası | ⬜ |

### Faz 5 — Genişleme

| Görev | Durum |
|---|---|
| T5.1 Grafana | ⬜ |
| T5.2 WinRM (JEA) | ⬜ |
| T5.3 NetScaler | ⬜ |
| T5.4 Azure DevOps | ⬜ |
| T5.5 Zincir takibi (K2) | ⬜ |

### Faz 6 — Üretim

| Görev | Durum |
|---|---|
| T6.1 Kimlik doğrulama | ⬜ |
| T6.2 Sır yönetimi | ⬜ |
| T6.3 Helm + CI | ⬜ |
| T6.4 Gözlemlenebilirlik | ⬜ |

---

## Açık Konular (karar/aksiyon bekleyen)

| # | Konu | Sahip | Not |
|---|---|---|---|
| A1 | Node 18+ yükseltmesi | Geliştirici | T0.5 bloke (ADR-12) |
| A2 | WinRM JEA endpoint onayı | Windows/Güvenlik ekibi | T5.2 bloke — talebi **erken aç**, süreç uzun sürebilir |
| A3 | Salt-okunur servis hesapları | DevOps | k8s SA, ES rolü, Grafana Viewer, AzDO PAT, NetScaler cmdpolicy — negatif testleri yapılıp [06-SECURITY.md](06-SECURITY.md)'ye kaydedilecek |
| A4 | vLLM uç noktası ve model adı | Geliştirici | `.env` doldurulacak; o zamana kadar `mock` sağlayıcı |
| A5 | İlk 10 uygulama listesi | Geliştirici | Bilgi tabanı doldurma önceliği ([05-KNOWLEDGE-BASE.md](05-KNOWLEDGE-BASE.md) §8). `knowledge/` altındaki 5 doküman **örnektir**, gerçek değerlerle değiştirilmeli |
| A6 | `config/environments.yaml` gerçek değerleri | Geliştirici | 6 ortam → 5 cluster / 2 ELK / 2 Grafana eşlemesi. `config/policy.yaml` allowlist'leri de (namespace / index / WinRM host) gerçek değerlerle gözden geçirilmeli |
| A7 | Docker Desktop başlatma | Geliştirici | T0.3 migration doğrulaması için gerekli |
| A8 | `config/winrm_commands.yaml` | Geliştirici | `policy.yaml` bu dosyayı işaret ediyor; T5.2'de yazılacak whitelist'li komut şablonları |

---

## Oturum Günlüğü

| Tarih | Yapılanlar |
|---|---|
| 2026-09-29 | Gereksinim toplama (3 tur soru), mimari ve yığın kararları |
| 2026-09-30 | AGENTS.md, ajan talimatları ve `docs/01–08` yazıldı |
| 2026-09-30 | **T0.1 tamamlandı** — workspace kuruldu, `tracehub` CLI çalışıyor, kalite kapıları yeşil |
| 2026-09-30 | **T0.2 tamamlandı** — config/logging/messages testleriyle doğrulandı (16 test) |
| 2026-09-30 | **T0.4 tamamlandı** — LLM/embedding istemcileri + MockLLM (52 test). Docker'sız ilerlendiği için T0.3 atlandı |
| 2026-09-30 | **T1.1 tamamlandı** — KB şeması, yükleyici, CLI ve 5 örnek doküman (78 test). Windows BOM sorunu yakalandı ve çözüldü |
| 2026-09-30 | **T2.1 tamamlandı** — MCP ortak katmanı: `@readonly_tool`, `Policy`, `redaction`, `ReadOnlyHttpClient`, `summarize`, `ToolContext` + AST değişmez testi (180 test). Redaction'da `DB_PASSWORD=` gibi önekli anahtarların maskelenmediği **gerçek açık** bulunup kapatıldı |
| 2026-09-30 | `web/preview/` eklendi — yönetime gösterim için tek dosyalık **statik arayüz taslağı**. Node/Vite gerektirmez, `python -m http.server 8080 --directory web/preview` ile açılır. Gerçek arayüz değildir (T0.5 ile gelecek), içindeki örnek vaka temsilidir |
