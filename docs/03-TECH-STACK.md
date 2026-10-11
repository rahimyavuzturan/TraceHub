# 03 — Teknoloji Yığını

Her seçim için gerekçe ve reddedilen alternatif yazılıdır. Bir seçimi değiştirmek
istiyorsan önce buradaki gerekçeyi çürüt, sonra [07-DECISIONS.md](07-DECISIONS.md)'e
yeni karar kaydı ekle.

---

## Backend

| Bileşen | Seçim | Gerekçe | Reddedilen alternatif |
|---|---|---|---|
| Dil | **Python 3.12+** | MCP, LLM, RAG ekosisteminin en olgun olduğu yer; ekibin aşina olduğu dil | TypeScript full-stack — MCP SDK olgun ama k8s/WinRM/ES istemcileri Python'da daha iyi |
| Orkestrasyon | **LangGraph** | `interrupt()` + checkpoint = plan-onay kapısı için birebir. Durum DB'ye yazılır, kullanıcı saatler sonra devam edebilir | PydanticAI (onay kapısı için kendimiz durum makinesi yazmamız gerekirdi), CrewAI (fazla soyut), ham döngü (checkpoint'i sıfırdan yazmak) |
| API | **FastAPI + SSE** | async, pydantic yerleşik, SSE ile canlı araştırma izi yayını basit | WebSocket (tek yönlü yayın için gereksiz karmaşık), Flask (async zayıf) |
| Paket yönetimi | **uv** (yoksa pip + venv) | monorepo workspace desteği, hızlı; proxy arkasında çalışır | Poetry (workspace desteği zayıf), sadece pip (workspace yok) |
| Kod kalitesi | **ruff + mypy --strict + pytest** | Tek araçta lint+format, strict tipleme AI üretimi kodda hata yakalar | black+flake8+isort (üç araç yerine bir) |
| Validasyon | **pydantic v2** | Ayarlar, LLM yapılandırılmış çıktı, API şemaları — hepsi tek modelde | dataclass + manuel doğrulama |

---

## Veri

| Bileşen | Seçim | Gerekçe | Reddedilen alternatif |
|---|---|---|---|
| Veritabanı | **PostgreSQL 16 + pgvector** | Tek veritabanı; ilişkisel veri + vektör arama + tam metin arama (tsvector) aynı yerde. Ayrı vektör DB işletme yükü getirir | Qdrant/Weaviate (ikinci sistem), SQLite (pgvector ve eşzamanlılık yok) |
| Migration | **Alembic** | SQLAlchemy ile standart | elle SQL |
| ORM | **SQLAlchemy 2.0 async** | asyncpg ile async, tip dostu 2.0 API | Tortoise, raw asyncpg |
| Arama | **Hibrit: BM25 (tsvector) + kosinüs (pgvector), RRF ile birleştirme** | Türkçe kısaltmalar ("msube", "BOA") vektör aramada kaybolur, BM25 yakalar. Anlamsal benzerliği de vektör yakalar. İkisi şart | Sadece vektör (kısaltma sorunu), sadece BM25 (anlamsal eşleşme yok) |

---

## Yapay Zeka

| Bileşen | Seçim | Gerekçe | Reddedilen alternatif |
|---|---|---|---|
| Strateji | **RAG + güçlü prompt/tool-use** | Bilgi tabanı sürekli değişir; fine-tune edilmiş model gün içinde bayatlar. Yeni bilgi eklemek = markdown dosyası eklemek | Fine-tune (maliyet + veri seti + bayatlama), LoRA (v2'de değerlendirilir) |
| LLM sunucusu | **vLLM** (OpenAI uyumlu API) | Kurum içi GPU'da yüksek verim, standart API sayesinde istemci kodu değişmez | Ollama (üretim verimi düşük), TGI |
| Model | **Qwen3-32B-Instruct** | Güçlü araç çağırma (tool calling), iyi Türkçe, 32B tek GPU'ya sığar | Llama 3.3 70B (Türkçe zayıf, daha çok VRAM), 7B sınıfı (araç seçimi yetersiz) |
| Gömme (embedding) | **BAAI/bge-m3** (1024 boyut) | Çok dilli, Türkçe güçlü, uzun bağlam | text-embedding-3 (bulut, kapalı ağda kullanılamaz), e5-multilingual |
| Test modeli | **MockLLM** (kendi yazdığımız) | CI'da GPU yok; deterministik cevaplarla graf testi | Gerçek model ile test (yavaş, belirsiz, CI'da imkânsız) |

**Neden fine-tune yok?** Bu bir bilgi problemi, davranış problemi değil.
Model zaten Kubernetes'i, log analizini biliyor; bilmediği şey *bizim* ortamımız.
O bilgi RAG ile verilir ve markdown güncellenince anında güncellenir.
Fine-tune edilseydi her wiki değişikliğinde yeniden eğitim gerekirdi.

---

## Araçlar (MCP)

| Bileşen | Seçim | Gerekçe |
|---|---|---|
| Protokol | **MCP (Python SDK 2.x)** | Standart araç arayüzü; ileride başka istemcilerden de kullanılabilir |
| Sunucular | **Hepsini kendimiz yazıyoruz** | Hazır sunucular lisanslı/ücretli olabilir; daha önemlisi salt-okunur garantisini *kodda* verememiz gerekiyor. Kendi yazdığımızda mutasyon fonksiyonu hiç var olmaz |
| Taşıma | **streamable-http** (üretim), **stdio** (geliştirme) | Kubernetes'te ayrı pod olarak çalıştırılabilir |
| Kubernetes | `kubernetes-asyncio` | async, resmi istemci |
| Elasticsearch | `elasticsearch-py` (read-only kullanıcı) | resmi istemci |
| WinRM | `pypsrp` + **JEA endpoint** | JEA = sunucu tarafında komut whitelist'i; savunmanın ilk katmanı |
| NetScaler | `httpx` + NITRO REST (sadece GET) | Hafif; NITRO iyi dokümante |
| Azure DevOps | `httpx` + REST API (read-scope PAT) | SDK ağır, sadece birkaç uç nokta lazım |

---

## Arayüz

| Bileşen | Seçim | Gerekçe |
|---|---|---|
| Çerçeve | **React 18 + Vite + TypeScript** | Hızlı geliştirme, geniş ekosistem |
| Veri | **TanStack Query** | Sunucu durumu yönetimi, SSE ile iyi çalışır |
| Stil | **Tailwind + shadcn/ui** | Hızlı, tutarlı; kopyalanan bileşenler — bağımlılık kilidi yok |
| Dil | **Türkçe** (i18n dosyasında) | Kullanıcı ekibi Türkçe |

> **Gereksinim:** Node 18+. Mevcut geliştirme makinesinde Node 16 var,
> arayüz çalışmasından önce yükseltilmeli.

---

## Dağıtım

| Bileşen | Seçim | Gerekçe |
|---|---|---|
| Paketleme | **Docker** (multi-stage) | Standart |
| Dağıtım | **Kubernetes + Helm** | Zaten k8s kullanılıyor |
| Sır yönetimi | **v1: şifreli .env (SOPS/age) → k8s Secret; v2: Vault adaptörü** | Vault kurulumu beklenmeden ilerlenebilsin |
| CI | **Azure Pipelines** | Kurumda mevcut |

---

## Bağımlılık Politikası

- Yeni bağımlılık eklemeden önce: gerçekten gerekli mi, bakımı sürüyor mu, lisansı uygun mu?
- Kapalı ağ nedeniyle her bağımlılık proxy üzerinden indirilebilir olmalı.
- Bir işi 20 satır kodla yapabiliyorsak kütüphane eklemiyoruz.
