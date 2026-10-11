# 02 — Mimari

## 1. Katmanlar

```
┌──────────────────────────────────────────────────────────────┐
│ 1. Web Arayüzü (React + Vite + TS)                           │
│    Chat · Plan onay kartı · Canlı araştırma izi · Rapor · KB │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP + SSE
┌───────────────────────────▼──────────────────────────────────┐
│ 2. API (FastAPI)                                             │
│    Oturum · Kimlik (JWT) · SSE yayını · Audit yazımı         │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│ 3. Orkestratör (LangGraph)                                   │
│    intake → normalize → kb_retrieve → plan → [ONAY KAPISI]   │
│      → investigate (döngü) → synthesize → report → case      │
└──────────┬──────────────────────────────┬────────────────────┘
           │                              │
┌──────────▼───────────┐      ┌───────────▼────────────────────┐
│ 4. MCP Host          │      │ 7. LLM Katmanı                 │
│  Sunucu keşfi        │      │  vLLM (Qwen3-32B) · bge-m3     │
│  Araç kataloğu       │      │  MockLLM (test)                │
│  Çağrı + audit       │      └────────────────────────────────┘
└──────────┬───────────┘
           │ MCP (stdio / streamable-http)
┌──────────▼───────────────────────────────────────────────────┐
│ 5. MCP Sunucuları — HEPSİ SALT OKUNUR                        │
│  k8s · elastic · grafana · winrm · netscaler · azdo · kb     │
│  Ortak katman: guard · policy · redaction · budget · audit   │
└──────────┬───────────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────────────┐
│ 6. Veri (PostgreSQL 16 + pgvector)                           │
│  kb_documents · kb_chunks · sessions · plans · tool_calls    │
│  cases · audit_events · users                                │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Ana Akış

```
 [Kullanıcı talebi]
        │
        ▼
 ┌─────────────┐   Talep metni temizlenir, ortam/uygulama ipuçları çıkarılır
 │  normalize  │   (LLM + kural tabanlı; "prep" → preprod, "dmz" → dmz-*)
 └──────┬──────┘
        ▼
 ┌─────────────┐   service_catalog + topology + benzer cases
 │ kb_retrieve │   hibrit arama (BM25 + vektör, RRF)
 └──────┬──────┘
        ▼
 ┌─────────────┐   Yapılandırılmış plan üretilir:
 │    plan     │   [{adım, araç, parametreler, ortam, gerekçe, maliyet}]
 └──────┬──────┘
        ▼
 ╔═════════════╗   LangGraph interrupt() — akış DURUR, durum DB'ye yazılır
 ║ ONAY KAPISI ║   Kullanıcı: onayla | düzenle | reddet
 ╚══════╤══════╝
        │ onaylandı
        ▼
 ┌─────────────┐   Döngü: araç çağır → gözlem → değerlendir → devam/bitir
 │ investigate │   Bütçe: adım sayısı, süre, çıktı boyutu
 └──────┬──────┘   Plan dışına çıkma gerekirse → tekrar ONAY KAPISI
        ▼
 ┌─────────────┐   Bulgular + kanıt alıntıları + kök neden hipotezleri
 │  synthesize │   + önerilen adımlar + uyarılar (onay/prod/geri alma)
 └──────┬──────┘
        ▼
 ┌─────────────┐   Vaka hafızasına yaz (semptom → kök neden → çözüm)
 │    case     │
 └─────────────┘
```

**Kritik tasarım kararı:** Onay kapısı `LangGraph.interrupt()` ile yapılır.
Akış gerçekten durur, durum checkpoint'e yazılır, kullanıcı saatler sonra bile
devam ettirebilir. Sahte bir "onay bekliyormuş gibi yapma" değil.

---

## 3. Dizin Yapısı

```
TraceHub/
├─ AGENTS.md                      # kod yazan ajanlar için zorunlu okuma
├─ README.md
├─ pyproject.toml                 # workspace kökü, ruff/mypy/pytest ayarları
├─ docker-compose.yml             # postgres + pgvector (geliştirme)
├─ .env.example                   # ayar şablonu — GERÇEK SIR COMMIT EDİLMEZ
├─ alembic.ini
│
├─ docs/                          # bu dokümanlar
│  ├─ 01-PROJECT-PLAN.md
│  ├─ 02-ARCHITECTURE.md
│  ├─ 03-TECH-STACK.md
│  ├─ 04-WORK-BREAKDOWN.md
│  ├─ 05-KNOWLEDGE-BASE.md
│  ├─ 06-SECURITY.md
│  ├─ 07-DECISIONS.md
│  └─ 08-STATUS.md
│
├─ .github/instructions/          # dosya bazlı kodlama kuralları
│  ├─ python.instructions.md
│  └─ mcp-server.instructions.md
│
├─ packages/
│  ├─ tracehub-core/              # config, logging, db, llm, embedding, messages
│  │  └─ tracehub_core/
│  │     ├─ config.py             # pydantic-settings — TEK ayar kaynağı
│  │     ├─ logging.py            # structlog, stderr'e yazar
│  │     ├─ messages.py           # kullanıcıya görünen TÜRKÇE metinler
│  │     ├─ cli.py                # `tracehub` komutu
│  │     ├─ db/                   # base.py, models.py
│  │     └─ llm/                  # client.py, mock.py, embedding.py
│  │
│  ├─ tracehub-kb/                # bilgi tabanı
│  │  └─ tracehub_kb/
│  │     ├─ schema.py             # frontmatter pydantic modelleri
│  │     ├─ loader.py             # markdown okuma + doğrulama
│  │     ├─ chunker.py            # başlık duyarlı parçalama
│  │     ├─ ingest.py             # knowledge/ → pgvector
│  │     └─ search.py             # hibrit arama (BM25 + vektör, RRF)
│  │
│  ├─ tracehub-api/               # FastAPI
│  │  └─ tracehub_api/
│  │     ├─ main.py
│  │     ├─ deps.py
│  │     ├─ routers/              # health, auth, sessions, kb, agent(SSE), audit
│  │     └─ schemas/
│  │
│  ├─ tracehub-agent/             # LangGraph
│  │  └─ tracehub_agent/
│  │     ├─ state.py              # graf durumu (pydantic)
│  │     ├─ graph.py              # düğüm bağlantıları
│  │     ├─ nodes/                # normalize, kb_retrieve, plan, investigate, report
│  │     ├─ prompts/              # TÜRKÇE sistem promptları
│  │     └─ mcp_host.py           # MCP sunucularına bağlanma, araç kataloğu
│  │
│  ├─ tracehub-mcp-common/        # MCP ortak katmanı
│  │  └─ tracehub_mcp_common/
│  │     ├─ guard.py              # @readonly_tool dekoratörü
│  │     ├─ policy.py             # allowlist, prod işaretleme, bütçe
│  │     ├─ redaction.py          # sır/PII maskeleme
│  │     ├─ http.py               # ReadOnlyHttpClient (GET/HEAD allowlist)
│  │     ├─ summarize.py          # çıktı kırpma
│  │     └─ context.py            # ToolContext
│  │
│  ├─ tracehub-mcp-k8s/
│  ├─ tracehub-mcp-elastic/
│  ├─ tracehub-mcp-grafana/       # Faz 5
│  ├─ tracehub-mcp-winrm/         # Faz 5
│  ├─ tracehub-mcp-netscaler/     # Faz 5
│  └─ tracehub-mcp-azdo/          # Faz 5
│
├─ knowledge/                     # bilgi tabanı (git'te versiyonlu markdown)
│  ├─ service_catalog/
│  ├─ topology/
│  ├─ runbooks/
│  ├─ cases/
│  ├─ glossary/
│  └─ imported/                   # AzDO Wiki'den çekilen (git'te YOK)
│
├─ config/
│  ├─ policy.yaml                 # ortam/namespace/index/host allowlist
│  ├─ environments.yaml           # ortam → cluster/ELK/Grafana eşlemesi
│  └─ winrm_commands.yaml         # whitelist'li komut şablonları
│
├─ migrations/                    # alembic
├─ web/                           # React + Vite + TS
└─ tests/
   ├─ test_readonly_invariant.py  # AST taraması — mutasyon fonksiyonu yok
   ├─ golden/                     # kaydedilmiş araç cevapları, offline replay
   └─ ...
```

---

## 4. Veritabanı Şeması

| Tablo | Amaç | Önemli alanlar |
|---|---|---|
| `users` | Yerel kimlik | id, username, password_hash (argon2), role |
| `sessions` | Araştırma oturumu | id, user_id, title, status, created_at |
| `messages` | Chat geçmişi | id, session_id, role, content, created_at |
| `plans` | Üretilen planlar | id, session_id, status (pending/approved/rejected/edited), raw_json |
| `plan_steps` | Plan adımları | id, plan_id, order, tool_name, parameters, environment, rationale, cost |
| `tool_calls` | Gerçekleşen çağrılar | id, session_id, plan_step_id, tool, params, duration_ms, status, output_summary |
| `kb_documents` | Bilgi tabanı dokümanı | id, path, doc_type, title, frontmatter, content_hash, updated_at |
| `kb_chunks` | Parçalar + gömme | id, document_id, ordinal, heading_path, content, embedding vector(1024), tsv |
| `cases` | Vaka hafızası | id, session_id, symptom, root_cause, resolution, tags, embedding |
| `audit_events` | Denetim izi | id, actor, action, environment, target, params_redacted, created_at |

İndeksler:

- `kb_chunks.embedding` → HNSW (cosine)
- `kb_chunks.tsv` → GIN (tsvector, Türkçe + simple sözlük)
- `audit_events.created_at` → BRIN

---

## 5. Ortam Modeli

Ortam sayısı: **prod, preprod, test** × **internal / DMZ** = 6 mantıksal ortam.
Altyapı: 5 Kubernetes cluster, 20+ namespace, 2 ELK, 2 Grafana.

`config/environments.yaml` her mantıksal ortamı fiziksel hedeflere eşler:

```yaml
environments:
  prod:
    display_name: "Üretim"
    is_production: true
    k8s_context: prod-cluster
    elastic: elastic-prod
    grafana: grafana-prod
    namespaces: [payments, mobile, integration]
  dmz-preprod:
    display_name: "DMZ Ön Üretim"
    is_production: false
    k8s_context: dmz-cluster
    elastic: elastic-prod
    grafana: grafana-prod
    namespaces: [dmz-mobile-prep]
```

Her araç çağrısında `environment` parametresi **zorunlu**. Allowlist'te yoksa reddedilir.
`is_production: true` olan ortamlar raporlarda ve onay kartında görsel olarak işaretlenir.

---

## 6. MCP Araç Kataloğu (planlanan)

| Sunucu | Araçlar | Faz |
|---|---|---|
| `kb` | `kb_search`, `kb_get_document`, `kb_similar_cases` | 1 |
| `k8s` | `list_namespaces`, `list_pods`, `describe_pod`, `pod_logs`, `previous_pod_logs`, `list_events`, `deployment_status`, `resource_usage` | 2 |
| `elastic` | `list_indices`, `search_logs`, `error_aggregation`, `sample_documents`, `trace_by_correlation_id` | 2 |
| `grafana` | `search_dashboards`, `get_panel_data`, `list_alert_rules`, `list_annotations` | 5 |
| `winrm` | `service_status`, `event_log`, `iis_app_pool_status`, `disk_usage`, `listening_ports`, `file_tail` | 5 |
| `netscaler` | `find_vserver`, `vserver_status`, `servicegroup_members`, `member_health`, `bound_certificate` | 5 |
| `azdo` | `find_repository`, `recent_commits`, `pipeline_status`, `find_work_item`, `wiki_search` | 5 |

Araç sayısı bilinçli olarak sınırlı tutulur — yerel modelin araç seçim kalitesi
araç sayısı arttıkça düşer.

---

## 7. Gözlemlenebilirlik

- **Log**: structlog, JSON, stderr. Her isteğe `request_id`, her oturuma `session_id` bağlanır.
- **Audit**: Her araç çağrısı `audit_events` tablosuna yazılır (parametreler redaction'dan geçmiş).
- **Metrik**: Araç gecikmesi, token tüketimi, adım sayısı, onay/red oranı.
- **Trace**: OpenTelemetry (Faz 6).
