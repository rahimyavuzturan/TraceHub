# 06 — Güvenlik

## 1. Altın Kural

> **TraceHub hedef sistemlerde asla değişiklik yapmaz.**

Bu bir "niyet" değil, mimari bir kısıttır. Durum değiştiren kod **yazılmaz**;
yazılmadığı için yanlışlıkla çağrılması da mümkün olmaz.

---

## 2. Üç Katmanlı Savunma

Tek katman yeterli değildir. Üçü de uygulanır.

### Katman 1 — Kimlik (hedef sistemlerde)

Servis hesaplarının **teknik olarak** yazma yetkisi yoktur. Kod hatalı olsa bile
sistem reddeder.

| Sistem | Yetkilendirme |
|---|---|
| Kubernetes | `view` ClusterRole ile bağlı ServiceAccount. `pods/exec`, `pods/attach`, `pods/portforward` **yok** |
| Elasticsearch | `read` + `view_index_metadata` ayrıcalıklı özel rol, sadece izinli index kalıpları |
| Grafana | `Viewer` rolünde servis hesabı |
| Azure DevOps | PAT: `Code (Read)`, `Build (Read)`, `Work Items (Read)`, `Wiki (Read)` — başka scope yok |
| NetScaler | Salt-okunur `cmdpolicy` (`^(show|stat)\s`) atanmış kullanıcı |
| Windows | **JEA** (Just Enough Administration) endpoint — sunucu tarafında komut whitelist'i |

> Bu hesaplar kurulurken **negatif test** yapılır: bilerek bir yazma denemesi
> yapılır ve 403 alındığı doğrulanır. Test sonucu buraya kaydedilir.

### Katman 2 — Kod (`tracehub-mcp-common`)

- `@readonly_tool` dekoratörü: aracı kategori ve maliyetle işaretler, audit kaydı üretir.
- `ReadOnlyHttpClient`: yalnızca `GET` ve `HEAD`.
  **Tek istisna:** Elasticsearch `_search` ve `_count` uç noktaları (gövde gerektirdiği
  için POST kullanır). Bu istisna kodda açıkça allowlist'lenmiştir, başka yerde POST edilemez.
- Kubernetes istemcisinde `exec`, `attach`, `port-forward` API'leri **import bile edilmez**.
- WinRM'de serbest komut yok; yalnızca `config/winrm_commands.yaml` içindeki
  parametreli şablonlar.
- **AST invariant testi** (`tests/test_readonly_invariant.py`): tüm MCP paketlerini
  tarar, şu ön eklerle başlayan fonksiyon bulursa testi düşürür:
  `create_`, `update_`, `patch_`, `delete_`, `apply_`, `put_`, `post_`, `restart_`,
  `scale_`, `exec_`, `drain_`, `cordon_`, `rollout_`, `remove_`, `set_`.
  Ayrıca `subprocess`, `os.system`, `shell=True` kullanımını yasaklar.

### Katman 3 — Politika (`config/policy.yaml`)

Kod doğru olsa bile politika kapıyı daraltır:

```yaml
environments:
  allowed: [prod, preprod, test, dmz-prod, dmz-preprod, dmz-test]
  production: [prod, dmz-prod]        # raporlarda işaretlenir

kubernetes:
  namespaces:
    allow: ["mobile", "payments", "integration", "dmz-*"]
    deny: ["kube-system", "kube-public", "cattle-*"]
  limits:
    max_tail_lines: 2000
    max_since_minutes: 1440

elasticsearch:
  indices:
    allow: ["*-web-*", "*-api-*", "app-*"]
    deny: ["security-*", "audit-*", ".*"]
  limits:
    max_size: 200
    max_window_minutes: 1440
    require_time_window: true         # zaman penceresi ZORUNLU

winrm:
  hosts:
    allow: ["SDL*", "STL*", "SXL*"]   # sadece test/preprod önekleri
  commands_file: config/winrm_commands.yaml

rate_limit:
  tool_calls_per_minute: 30
  tool_calls_per_session: 200
```

Her araç çağrısının **ilk satırı** `ctx.policy.assert_allowed(...)` olmalıdır.

---

## 3. Sır Yönetimi

| Kural | Uygulama |
|---|---|
| Sır koda girmez | `.env` / k8s Secret; `.gitignore`'da |
| Sır loglanmaz | `structlog` işlemcisi + `SecretStr` tipleri |
| Sır LLM'e gitmez | Her araç çıktısı `redact()` içinden geçer |
| Sır arayüzde görünmez | Audit görüntüleyicide parametreler maskelenmiş |
| v1 | SOPS/age ile şifreli dosya → k8s Secret |
| v2 | HashiCorp Vault adaptörü |

### Redaction kapsamı

- Bearer token, JWT, API key, PAT (`ghp_`, `pat_`, base64 uzun dizeler)
- `password=`, `pwd=`, `connectionstring=` kalıpları
- Özel anahtar blokları (`-----BEGIN ... PRIVATE KEY-----`)
- TCKN (11 hane), kart numarası (Luhn), IBAN
- E-posta adresleri (kişisel veri)

Redaction **LLM'e göndermeden önce** ve **veritabanına yazmadan önce** uygulanır.

---

## 4. Enjeksiyon Savunması

Kullanıcı girdisi ve **LLM çıktısı** güvenilmezdir.

| Hedef | Kural |
|---|---|
| SQL | Parametreli sorgu. String birleştirme yok |
| Elasticsearch DSL | Sözlük/nesne olarak kurulur, string olarak değil. Alan adları allowlist'ten |
| Shell | Hiç kullanılmaz. `subprocess`, `os.system`, `shell=True` yasak |
| WinRM | Serbest komut yok; şablon + parametre kaçışı |
| Kubernetes | Kaynak adları düzenli ifade ile doğrulanır (RFC 1123) |
| HTTP | URL'ler yapılandırmadan gelir; LLM'in ürettiği URL'e istek atılmaz (SSRF) |

### Prompt injection

Araç çıktıları (log satırları, ES dokümanları) LLM bağlamına girer ve içlerinde
kötü niyetli talimat bulunabilir. Savunma:

- Araç çıktıları bağlamda **veri** olarak işaretlenir, talimat olarak değil.
- Ajan yalnızca kayıtlı araçları çağırabilir; araç adı doğrulanır.
- Araç çıktısı yeni bir araç çağrısını "yetkilendiremez" — plan dışına çıkış
  her zaman **kullanıcı onayına** döner.
- Zaten tüm araçlar salt okunur olduğu için başarılı bir injection'ın etkisi sınırlıdır.

---

## 5. Denetim (Audit)

Her araç çağrısı `audit_events` tablosuna yazılır:

| Alan | İçerik |
|---|---|
| `actor` | Kullanıcı adı |
| `session_id` | Oturum |
| `action` | Araç adı |
| `environment` | Hedef ortam |
| `target` | Namespace/index/host |
| `params_redacted` | Parametreler (maskelenmiş) |
| `status` | ok / denied / error |
| `duration_ms` | Süre |
| `created_at` | Zaman |

Audit kaydı **araç çalışmadan önce** başlatılır, sonra sonuçla güncellenir —
böylece reddedilen ve hata veren çağrılar da iz bırakır.

---

## 6. Kimlik Doğrulama (uygulama tarafı)

- v1: yerel kullanıcılar, **argon2id** parola özeti, JWT (kısa ömürlü).
- Roller: `viewer` (okuma + arama), `operator` (araştırma başlatma, plan onaylama).
- Prod ortamına dokunan planları yalnızca `operator` onaylayabilir.
- v2: LDAP/AD (kapsam dışı, [01-PROJECT-PLAN.md](01-PROJECT-PLAN.md) §3.3).

---

## 7. Güvenlik Kontrol Listesi (her PR öncesi)

- [ ] Yeni bir mutasyon fonksiyonu eklenmedi (`pytest tests/test_readonly_invariant.py`)
- [ ] Yeni araçta `ctx.policy.assert_allowed(...)` ilk satırda
- [ ] Zaman penceresi / limit parametreleri zorunlu ve dar varsayılanlı
- [ ] Çıktı `redact()` içinden geçiyor
- [ ] Sır loglanmıyor, `SecretStr` kullanılmış
- [ ] SQL parametreli, ES DSL nesne olarak kurulmuş
- [ ] `subprocess` / `shell=True` yok
- [ ] Yeni ortam/namespace/index eklendiyse `config/policy.yaml` güncellendi
- [ ] Audit kaydı üretiliyor
