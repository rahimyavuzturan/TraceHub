# 04 — İş Kırılımı (Work Breakdown)

Her görev **tek oturumda bitirilebilecek**, bağımsız test edilebilir ve tek bir AI kod
ajanına verilebilecek boyutta tanımlanmıştır.

**Görev formatı:** her görevde *Amaç*, *Üretilecek dosyalar*, *Kabul kriterleri*, *Bağımlılık* vardır.

**Çalışma kuralı:** Bir göreve başlarken [08-STATUS.md](08-STATUS.md)'i "devam ediyor" olarak
işaretle, bitirince "tamam" yap ve kısa not düş.

---

## Faz 0 — İskelet

### T0.1 · Monorepo iskeleti
- **Amaç:** Workspace yapısı, kalite araçları, geliştirme veritabanı ayağa kalksın.
- **Üretilecek:** `pyproject.toml` (ruff/mypy/pytest ayarları), `docker-compose.yml`
  (postgres+pgvector), `.env.example`, `.gitignore`, `packages/` boş paket iskeletleri.
- **Kabul:** `pip install -e ".[dev]"` çalışır · `ruff check .` temiz · `pytest -q` (boş) geçer ·
  `docker compose up -d` sonrası veritabanına bağlanılır.
- **Bağımlılık:** —

### T0.2 · Çekirdek: config + logging + messages
- **Amaç:** Tek ayar kaynağı ve stderr'e yazan yapılandırılmış loglama.
- **Üretilecek:** `tracehub_core/config.py` (pydantic-settings, `TRACEHUB_` öneki, iç içe ayarlar),
  `tracehub_core/logging.py` (structlog, **stderr**), `tracehub_core/messages.py` (Türkçe metinler).
- **Kabul:** Ayarlar ortam değişkeni ile geçersiz kılınabiliyor · log satırı stdout'a **değil**
  stderr'e gidiyor (MCP stdio için kritik) · `mypy --strict` temiz.
- **Bağımlılık:** T0.1

### T0.3 · Veritabanı şeması + migration
- **Amaç:** [02-ARCHITECTURE.md](02-ARCHITECTURE.md#4-veritabanı-şeması) §4'teki tablolar.
- **Üretilecek:** `tracehub_core/db/base.py`, `tracehub_core/db/models.py`, `alembic.ini`,
  `migrations/` ilk revizyon (pgvector eklentisi + HNSW + GIN indeksleri).
- **Kabul:** `alembic upgrade head` temiz veritabanında çalışır · `alembic downgrade base` geri alır ·
  vector ve tsvector sütunları oluşur.
- **Bağımlılık:** T0.2

### T0.4 · LLM ve embedding istemcileri + MockLLM
- **Amaç:** Model sunucusu olmadan da geliştirme yapılabilsin.
- **Üretilecek:** `tracehub_core/llm/client.py` (OpenAI uyumlu, araç çağırma + yapılandırılmış çıktı),
  `tracehub_core/llm/mock.py` (senaryo tabanlı deterministik), `tracehub_core/llm/embedding.py`
  (bge-m3 istemcisi + `hash` sağlayıcı — geliştirme için deterministik sahte gömme).
- **Kabul:** `TRACEHUB_LLM__PROVIDER=mock` ile GPU'suz test geçer · araç çağırma cevabı
  pydantic modeline çözümlenir · zaman aşımı ve yeniden deneme davranışı test edilir.
- **Bağımlılık:** T0.2

### T0.5 · Arayüz iskeleti
- **Amaç:** Chat sayfası ve SSE bağlantısı.
- **Üretilecek:** `web/` (Vite + React + TS + Tailwind), chat sayfası, `useEventStream` kancası,
  Türkçe i18n dosyası.
- **Kabul:** `npm run dev` açılır · API `/health` çağrısı görünür · SSE test akışı ekrana düşer.
- **Bağımlılık:** T0.1 · **Node 18+ gerekir** (mevcut makinede Node 16 — önce yükselt)

---

## Faz 1 — Bilgi Tabanı

> Bu faz ajan olmadan da değerlidir: "bu uygulama nerede koşuyor?" sorusunu cevaplar.

### T1.1 · Bilgi tabanı şeması + doğrulayıcı
- **Amaç:** Markdown dokümanlarının frontmatter yapısı ve doğrulanması.
- **Üretilecek:** `tracehub_kb/schema.py` (doküman tipi başına pydantic modeli),
  `tracehub_kb/loader.py`, `tracehub kb validate` komutu, `knowledge/` altına **5 örnek doküman**
  (her tipten bir tane). Şema tanımı: [05-KNOWLEDGE-BASE.md](05-KNOWLEDGE-BASE.md).
- **Kabul:** Bozuk frontmatter için satır numaralı **Türkçe** hata mesajı · `tracehub kb validate`
  sıfır hata ile döner · her doküman tipi için birim testi.
- **Bağımlılık:** T0.2

### T1.2 · Parçalama + gömme + ingest
- **Amaç:** `knowledge/` → pgvector.
- **Üretilecek:** `tracehub_kb/chunker.py` (başlık duyarlı; başlık yolu parçada korunur),
  `tracehub_kb/ingest.py` (içerik hash'i ile değişmeyen dokümanı atlar), `tracehub kb ingest` komutu.
- **Kabul:** İki kez çalıştırınca ikinci sefer 0 doküman işler (idempotent) · silinen doküman
  veritabanından da silinir · parça sınırları başlık ortasından geçmez.
- **Bağımlılık:** T1.1, T0.3, T0.4

### T1.3 · Hibrit arama
- **Amaç:** BM25 + vektör, RRF ile birleştirme.
- **Üretilecek:** `tracehub_kb/search.py`, `tracehub kb search "..."` komutu.
- **Kabul:** "msube" gibi kısaltma aramasında BM25 sonucu üstte · anlamsal sorguda
  ("mobil şube arızası") vektör sonucu yakalanır · doküman tipine göre filtre çalışır ·
  sonuçlar kaynak dosya + başlık yolu ile döner (kanıt gösterimi için şart).
- **Bağımlılık:** T1.2

### T1.4 · KB MCP sunucusu + arayüz arama sayfası
- **Amaç:** Bilgi tabanı ajana ve kullanıcıya açılsın.
- **Üretilecek:** `packages/tracehub-mcp-kb/` (`kb_search`, `kb_get_document`, `kb_similar_cases`),
  `web/` arama sayfası.
- **Kabul:** MCP sunucusu stdio ile ayağa kalkar · araç çıktısı özetlenmiş metin (ham JSON değil) ·
  arayüzden arama yapılıp doküman görüntülenir.
- **Bağımlılık:** T1.3, T2.1

### T1.5 · "Ham metin → taslak doküman" asistanı
- **Amaç:** Ekipten toplanan dağınık yazıları yapılandırılmış markdown'a çevirmek.
- **Üretilecek:** API uç noktası + arayüz sayfası: ham metin yapıştır → LLM doküman tipini
  belirler, frontmatter üretir, eksik alanları **soru olarak** sorar → kullanıcı düzenler →
  `knowledge/` altına kaydedilir.
- **Kabul:** Yapıştırılan serbest metinden geçerli frontmatter üretilir · kullanıcı onaylamadan
  dosya yazılmaz · üretilen dosya `kb validate`'ten geçer.
- **Bağımlılık:** T1.1, T0.4

### T1.6 · Azure DevOps Wiki içe aktarımı
- **Amaç:** Mevcut wiki içeriğini bilgi tabanına almak.
- **Üretilecek:** `tracehub kb import-azdo` komutu (read-only PAT, REST API),
  çıktı `knowledge/imported/` (git'te yok).
- **Kabul:** Sayfalar hiyerarşisiyle indirilir · frontmatter taslağı eklenir ·
  PAT loglanmaz · yalnızca GET istekleri yapılır.
- **Bağımlılık:** T1.1

---

## Faz 2 — MCP Temeli ve İlk Araçlar

### T2.1 · MCP ortak katmanı ⭐
- **Amaç:** Salt-okunur garantisinin kod katmanı. **Projenin en kritik paketi.**
- **Üretilecek:** `tracehub_mcp_common/`:
  - `guard.py` — `@readonly_tool(category, cost)` dekoratörü
  - `policy.py` — `config/policy.yaml` okur; ortam/namespace/index/host allowlist,
    prod işaretleme, limit üst sınırları
  - `redaction.py` — token/parola/PAT/TCKN/kart no/e-posta maskeleme
  - `http.py` — `ReadOnlyHttpClient`: sadece GET/HEAD; ES `_search`/`_count` açık istisna
  - `summarize.py` — çıktı kırpma, kırpıldığını belirtme
  - `context.py` — `ToolContext` (policy, logger, audit yazıcı)
- **Kabul:** `assert_allowed` allowlist dışı ortamda Türkçe hata fırlatır ·
  `ReadOnlyHttpClient.post()` ES istisnası dışında **hata verir** · redaction testi
  gerçekçi örneklerle geçer · `tests/test_readonly_invariant.py` (AST taraması) yazılır ve geçer.
- **Bağımlılık:** T0.2

### T2.2 · Kubernetes MCP sunucusu
- **Amaç:** 5 cluster üzerinde salt-okunur k8s erişimi.
- **Üretilecek:** `packages/tracehub-mcp-k8s/`: `list_namespaces`, `list_pods`, `describe_pod`,
  `pod_logs`, `previous_pod_logs`, `list_events`, `deployment_status`, `resource_usage`.
- **Kabul:** Her araç için mocklanmış test · `exec`/`attach`/`port-forward` API'si kodda **yok** ·
  ortam → kubeconfig context çözümlemesi `environments.yaml` üzerinden · CrashLoopBackOff
  pod'unda `previous_pod_logs` önceki container'ın logunu getirir · çıktılar özetlenmiş.
- **Bağımlılık:** T2.1

### T2.3 · Elasticsearch MCP sunucusu
- **Amaç:** 2 ELK üzerinde salt-okunur log arama.
- **Üretilecek:** `packages/tracehub-mcp-elastic/`: `list_indices`, `search_logs`,
  `error_aggregation`, `sample_documents`, `trace_by_correlation_id`.
- **Kabul:** **Zaman penceresi zorunlu** — parametresiz çağrı hata verir · `size` üst sınırı
  policy'den · index allowlist'i uygulanır · sorgu DSL'i string birleştirme ile **kurulmaz** ·
  hata kümeleme sonucu özet metin döner.
- **Bağımlılık:** T2.1

### T2.4 · MCP host katmanı
- **Amaç:** Ajanın araçlara ulaşması.
- **Üretilecek:** `tracehub_agent/mcp_host.py` — sunucu keşfi, araç kataloğu → LLM araç şeması,
  çağrı yürütme, hata yönetimi, audit yazımı.
- **Kabul:** Birden çok sunucu aynı anda bağlanır · araç adı çakışması önlenir (ön ek) ·
  sunucu çöktüğünde ajan çökmez, Türkçe hata mesajı döner · her çağrı `tool_calls` +
  `audit_events` tablolarına yazılır.
- **Bağımlılık:** T2.1, T0.3

---

## Faz 3 — Orkestrasyon

### T3.1 · Graf durumu + normalize düğümü
- **Amaç:** Serbest metinden ortam ve uygulama ipuçlarını çıkarmak.
- **Üretilecek:** `tracehub_agent/state.py`, `nodes/normalize.py`.
- **Kabul:** "prep" → preprod, "dmz" → dmz-* eşlemesi · uygulama adayları bilgi tabanı ile
  eşleştirilir · belirsizlik varsa **kullanıcıya soru sorar**, uydurmaz.
- **Bağımlılık:** T1.3, T0.4

### T3.2 · Bilgi getirme düğümü
- **Üretilecek:** `nodes/kb_retrieve.py` — service_catalog + topology + benzer vakalar.
- **Kabul:** Getirilen her parça kaynak dosya yolu ile birlikte duruma yazılır (kanıt zinciri) ·
  bağlam penceresi bütçesi aşılmaz.
- **Bağımlılık:** T3.1

### T3.3 · Plan üretme düğümü ⭐
- **Amaç:** Yapılandırılmış, denetlenebilir araştırma planı.
- **Üretilecek:** `nodes/plan.py`, `prompts/plan_tr.md`. Plan şeması: adım no, araç,
  parametreler, ortam, gerekçe, tahmini maliyet, prod mu.
- **Kabul:** LLM çıktısı pydantic ile doğrulanır; geçersizse **bir kez** düzeltme istenir ·
  planda olmayan araç adı reddedilir · her adımda gerekçe **Türkçe** ve anlaşılır ·
  prod adımları işaretli.
- **Bağımlılık:** T3.2, T2.4

### T3.4 · Onay kapısı ⭐
- **Amaç:** Kullanıcı onayı olmadan hiçbir sorgu çalışmasın.
- **Üretilecek:** `graph.py` içinde `interrupt()` · API: plan getir / onayla / düzenle / reddet ·
  arayüzde onay kartı.
- **Kabul:** Onay gelmeden tek bir araç çağrısı yapılmaz (test ile kanıtlanır) ·
  akış yeniden başlatıldığında checkpoint'ten devam eder · kullanıcı adım silebilir/
  parametre değiştirebilir · red durumunda oturum temiz kapanır.
- **Bağımlılık:** T3.3

### T3.5 · Araştırma döngüsü
- **Üretilecek:** `nodes/investigate.py` — araç çağır → gözlem → değerlendir → devam/bitir.
- **Kabul:** Bütçeler uygulanır (adım/süre/çıktı boyutu) · bütçe dolunca elde edilenle rapora
  geçer · **plan dışına çıkmak gerekirse tekrar onay kapısına döner** · araç hatası döngüyü
  kırmaz, gözlem olarak kaydedilir.
- **Bağımlılık:** T3.4

### T3.6 · Rapor düğümü
- **Üretilecek:** `nodes/report.py`, `prompts/report_tr.md`.
- **Kabul:** Rapor bölümleri: özet · bulgular (her biri **kanıt alıntısı** ve kaynakla) ·
  kök neden hipotezleri (güven derecesiyle) · önerilen adımlar · uyarılar (onay gerekli /
  prod / geri alma planı) · ilgili linkler. Kanıtsız iddia yok — her bulgu bir araç çıktısına
  veya bilgi tabanı dokümanına referans verir.
- **Bağımlılık:** T3.5

### T3.7 · SSE canlı iz + durdurma
- **Kabul:** Her düğüm geçişi ve araç çağrısı anlık arayüze düşer · "Durdur" butonu
  araştırmayı güvenle sonlandırır · bağlantı koparsa yeniden bağlanınca kaldığı yerden devam eder.
- **Bağımlılık:** T3.5, T0.5

### T3.8 · Audit görüntüleyici
- **Kabul:** Oturum bazında tüm araç çağrıları, parametreler (redaction'lı), süre ve sonuç
  listelenir · filtrelenebilir.
- **Bağımlılık:** T2.4, T0.5

---

## Faz 4 — Kabul Senaryosu K1

### T4.1 · Golden test altyapısı
- **Amaç:** Ajan davranışını gerçek sisteme bağlanmadan ölçmek.
- **Üretilecek:** `tests/golden/` — kaydedilmiş araç cevapları, beklenen kök neden;
  offline replay harness.
- **Kabul:** Ajan kaydedilmiş vakayı GPU ve gerçek sistem olmadan çalıştırır ·
  başarı ölçütü otomatik hesaplanır · CI'da çalışır.
- **Bağımlılık:** T3.6

### T4.2 · Türkçe prompt ve araç seçimi iyileştirmesi
- **Kabul:** Golden sette başarı oranı ölçülür ve iyileşir · araç docstring'leri
  "ne zaman kullanılır / ne zaman kullanılmaz" bilgisini içerir.
- **Bağımlılık:** T4.1

### T4.3 · Vaka hafızası
- **Üretilecek:** Çözülen oturumdan vaka kaydı üretme + benzer vaka getirme entegrasyonu.
- **Kabul:** Kullanıcı onaylarsa vaka `cases` tablosuna ve `knowledge/cases/` altına yazılır ·
  sonraki benzer talepte getirilir · sır içermez (redaction'dan geçer).
- **Bağımlılık:** T3.6, T1.3

---

## Faz 5 — Genişleme

### T5.1 · Grafana MCP sunucusu
`search_dashboards`, `get_panel_data`, `list_alert_rules`, `list_annotations`.
Viewer API anahtarı · sadece GET. **Bağımlılık:** T2.1

### T5.2 · WinRM MCP sunucusu ⚠️
`service_status`, `event_log`, `iis_app_pool_status`, `disk_usage`, `listening_ports`, `file_tail`.
Sadece `config/winrm_commands.yaml` içindeki **parametreli, whitelist'li** şablonlar.
Serbest komut yok, string birleştirme yok. Sunucu tarafında **JEA endpoint** şart.
**Not:** JEA kurulumu için güvenlik/Windows ekibinden onay gerekebilir — talebi erken aç.
**Bağımlılık:** T2.1

### T5.3 · NetScaler MCP sunucusu
`find_vserver`, `vserver_status`, `servicegroup_members`, `member_health`, `bound_certificate`.
NITRO REST, sadece GET, read-only cmdpolicy. **Bağımlılık:** T2.1

### T5.4 · Azure DevOps MCP sunucusu
`find_repository`, `recent_commits`, `pipeline_status`, `find_work_item`, `wiki_search`.
Read-scope PAT. **Bağımlılık:** T2.1

### T5.5 · Zincir takibi (Kabul Senaryosu K2) ⭐
- **Amaç:** NLB → web → integration → backend zincirini otomatik yürütmek.
- **Üretilecek:** Topoloji grafiği yürütücü; katman katman sağlık kontrolü, sağlıklı katmanı
  eleme, bozuk katmanda derinleşme.
- **Kabul:** "DMZ BOA prep mobilde arıza var" talebinde zincir doğru sırayla takip edilir ·
  sorunlu katman kanıtla raporlanır.
- **Bağımlılık:** T5.1–T5.4, T4.1

---

## Faz 6 — Üretim

### T6.1 · Kimlik doğrulama
Yerel kullanıcılar (argon2 + JWT), `viewer` / `operator` rolleri. **Bağımlılık:** T0.3

### T6.2 · Sır yönetimi
SOPS/age ile şifreli ayarlar → k8s Secret; Vault için adaptör arayüzü. **Bağımlılık:** T0.2

### T6.3 · Helm chart + CI
Multi-stage Docker imajları, Helm chart, Azure Pipelines (proxy üzerinden build).
**Bağımlılık:** T6.1, T6.2

### T6.4 · Gözlemlenebilirlik
OpenTelemetry trace, token/maliyet metrikleri, araç gecikme paneli. **Bağımlılık:** T6.3

---

## Bağımlılık Özeti

```
T0.1 ─┬─ T0.2 ─┬─ T0.3 ─┐
      │        ├─ T0.4 ─┤
      │        └─ T2.1 ─┼─ T2.2 ─┐
      └─ T0.5           │  T2.3 ─┤
                        │  T2.4 ─┤
               T1.1 ─ T1.2 ─ T1.3 ─┼─ T3.1 ─ T3.2 ─ T3.3 ─ T3.4 ─ T3.5 ─ T3.6
               T1.5 ─┘   T1.4 ─┘   │                                      │
               T1.6 ─┘             │                      T3.7 ─┘  T3.8 ─┘
                                   └─ T4.1 ─ T4.2 ─ T4.3 ─ T5.5
                                      T5.1 · T5.2 · T5.3 · T5.4 (paralel)
                                      T6.1 ─ T6.2 ─ T6.3 ─ T6.4
```

**Paralel çalışılabilir:** (T0.3, T0.4, T0.5) · (T2.2, T2.3) · (T1.4, T1.5, T1.6) ·
(T3.7, T3.8) · (T5.1, T5.2, T5.3, T5.4)
