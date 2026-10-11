# 05 — Bilgi Tabanı

Bilgi tabanı TraceHub'ın **en değerli** parçasıdır. Araçlar sistemlerin *anlık durumunu*
söyler; bilgi tabanı *nereye bakılacağını* ve *bunun ne anlama geldiğini* söyler.
İyi bir bilgi tabanı olmadan ajan kördür.

---

## 1. Temel İlkeler

1. **Git'te versiyonlu markdown.** Veritabanı türetilmiş veridir, kaynak dosyalardır.
   Bir bilgi yanlışsa dosyayı düzelt, yeniden ingest et.
2. **Her doküman frontmatter'lı.** Yapılandırılmış alanlar filtreleme ve eşleştirme sağlar.
3. **Türkçe yaz.** Ekip Türkçe konuşuyor, model Türkçe arıyor, kullanıcı Türkçe okuyor.
4. **Takma adları yaz.** Kullanıcı "mobil şube" der, sistem adı `msube-web`'dir.
   `aliases` alanı bu köprüyü kurar — **en sık atlanan ve en kritik alan**.
5. **Kısa ve kesin.** Belirsiz cümle ajanı yanlış yönlendirir. Bilmiyorsan yazma.

---

## 2. Doküman Tipleri

| Tip | Klasör | Cevapladığı soru |
|---|---|---|
| `service` | `knowledge/service_catalog/` | Bu uygulama nedir, nerede koşar, logları nerede? |
| `topology` | `knowledge/topology/` | İstek hangi katmanlardan geçer, bağımlılıklar ne? |
| `runbook` | `knowledge/runbooks/` | Bu işlem nasıl yapılır, hangi onaylar gerekir? |
| `case` | `knowledge/cases/` | Bu semptom daha önce görüldü mü, kök nedeni neydi? |
| `glossary` | `knowledge/glossary/` | Bu kısaltma/terim ne demek? |

---

## 3. Frontmatter Şemaları

### 3.1 Ortak alanlar (her tipte)

```yaml
type: service | topology | runbook | case | glossary   # zorunlu
title: "Mobil Şube Web"                                 # zorunlu
aliases: ["mobil şube", "msube", "mobil banka"]         # KRİTİK — kullanıcı dili
tags: ["mobil", "boa", "dmz"]
owner: "DevOps"                                         # sorumlu ekip
updated: 2026-09-30                                     # zorunlu
confidence: high | medium | low                         # bilginin güvenilirliği
```

> `confidence: low` olan dokümanlar rapora "doğrulanmalı" notuyla girer.

### 3.2 `service`

```yaml
type: service
title: "Mobil Şube Web"
aliases: ["mobil şube", "msube", "mobil banka"]
updated: 2026-09-30
confidence: high

repository:
  platform: azure-devops
  project: "KT"
  path: "KT/BOA/msube-web"
  url: "https://dev.azure.com/..."

deployments:                       # ortam başına bir kayıt
  - environment: prod
    cluster: prod-cluster
    namespace: mobile
    workload: msube-web
    kind: Deployment
  - environment: dmz-preprod
    cluster: dmz-cluster
    namespace: dmz-mobile-prep
    workload: msube-web
    kind: Deployment

observability:
  elastic_indices: ["msube-web-*"]
  grafana_dashboards: ["Mobil Şube Genel"]
  log_format: json
  correlation_field: "traceId"       # zincir takibi için önemli

network:
  netscaler_vservers: ["vs_msube_prep_443"]
  ingress_hosts: ["msubetest.kuveytturk.com.tr"]

depends_on: ["boa-integration", "boa-backend"]   # başka service dokümanlarının slug'ları
contacts:
  - team: "Mobil Uygulama Geliştirme"
    channel: "Teams / Mobil Ekip"
```

### 3.3 `topology`

```yaml
type: topology
title: "DMZ Mobil İstek Zinciri"
aliases: ["dmz mobil akış", "mobil prep zinciri"]
updated: 2026-09-30
confidence: high

chain:                              # sıra ÖNEMLİ — ajan bu sırayla ilerler
  - layer: netscaler
    name: "vs_msube_prep_443"
    environment: dmz-preprod
    check: "vserver ve member durumları UP mı?"
  - layer: web
    service: msube-web
    environment: dmz-preprod
    check: "pod durumu, 5xx oranı"
  - layer: integration
    service: boa-integration
    environment: dmz-preprod
    check: "backend çağrı hataları, timeout"
  - layer: backend
    service: boa-backend
    environment: preprod
    check: "servis durumu, event log, bağlantı havuzu"
```

### 3.4 `runbook`

```yaml
type: runbook
title: "Azure DevOps Repo Silme Prosedürü"
aliases: ["repo silme", "repository kaldırma"]
updated: 2026-09-30
confidence: high

applies_to: ["azure-devops"]
approvals_required:                # rapor sonunda UYARI olarak gösterilir
  - "Repo sahibi ekip yöneticisi onayı"
  - "Mercek üzerinden değişiklik talebi"
risk: high
reversible: false                  # geri alınamaz işlemler özel uyarı alır
```

Gövde: numaralı adımlar, ön koşullar, doğrulama adımları, geri alma (varsa).

### 3.5 `case`

```yaml
type: case
title: "msube-web CrashLoopBackOff — eksik ConfigMap anahtarı"
aliases: []
updated: 2026-09-30
confidence: high

symptom: "Pod sürekli yeniden başlıyor, previous log'da KeyNotFoundException"
environment: dmz-preprod
services: ["msube-web"]
root_cause: "ConfigMap'te BackendUrl anahtarı yoktu (deploy sırasında eklenmemiş)"
resolution: "ConfigMap'e anahtar eklendi, deployment yeniden başlatıldı"
detection_signals:                 # ajanın eşleştirme yapabilmesi için
  - "CrashLoopBackOff"
  - "KeyNotFoundException"
  - "ConfigMap"
time_to_resolve_minutes: 35
```

### 3.6 `glossary`

```yaml
type: glossary
title: "Kurum Kısaltmaları"
updated: 2026-09-30
confidence: high
```

Gövde: `**BOA** — ...` biçiminde tanım listesi. Her terim kendi başlığı altında olmalı
(parçalama başlık duyarlı çalışır).

---

## 4. Yazım Rehberi

### İyi

```markdown
## Loglar

Uygulama JSON formatında `stdout`'a loglar. ELK'de `msube-web-*` index'inde toplanır.
Korelasyon alanı `traceId`. Hata seviyesi `level: ERROR`.

Sık görülen hata: `BackendTimeoutException` — integration katmanı backend'e
5 saniyede ulaşamadığında oluşur, genellikle backend tarafında sorun vardır.
```

### Kötü

```markdown
## Loglar

Loglar ELK'de. Bakabilirsiniz.
```

Kurallar:

- Somut isim yaz: index adı, namespace, alan adı, hata sınıfı.
- "Genellikle X olur çünkü Y" gibi **nedensel** bilgi yaz — ajanın hipotez kurmasını sağlar.
- Ekran görüntüsü yerine metin yaz (model okuyamaz).
- Sır yazma: parola, token, bağlantı dizesi **asla**.
- Kişi adı yerine ekip/kanal yaz.

---

## 5. Parçalama (Chunking)

- Başlık duyarlı: `##` ve `###` sınırlarında bölünür.
- Her parça kendi **başlık yolunu** taşır (`Mobil Şube Web > Loglar`) — arama sonucunda
  kanıt olarak gösterilir.
- Hedef ~700 token, ~100 token örtüşme.
- Frontmatter her parçaya metadata olarak eklenir (filtreleme için).

---

## 6. Arama

Hibrit: **BM25 (tsvector)** + **kosinüs (pgvector)**, RRF ile birleştirilir.

| Sorgu tipi | Hangisi yakalar |
|---|---|
| "msube" (kısaltma) | BM25 |
| "mobil şube arızası" (anlamsal) | Vektör |
| "CrashLoopBackOff ConfigMap" (teknik terim) | BM25 |
| "ödeme yapılamıyor" (belirti) | Vektör |

Bu yüzden ikisi de şart. Sadece vektör arama Türkçe kısaltmalarda başarısız olur.

---

## 7. İçerik Toplama Akışı

Ekipten gelen bilgi dağınık ve yarı yapılandırılmış olacak. Akış:

```
Ekip üyesinin yazdığı serbest metin
        │
        ▼  T1.5 asistanı
LLM doküman tipini belirler, frontmatter taslağı üretir,
eksik alanları SORU olarak sorar
        │
        ▼
Kullanıcı düzeltir/tamamlar  ← onay olmadan dosya YAZILMAZ
        │
        ▼
knowledge/<tip>/<slug>.md    → git commit
        │
        ▼  tracehub kb ingest
pgvector
```

Azure DevOps Wiki içeriği T1.6 ile `knowledge/imported/` altına çekilir; oradan
gözden geçirilip kalıcı klasörlere taşınır. `imported/` git'e girmez (ham, doğrulanmamış).

---

## 8. Öncelik Sırası (ilk doldurulacaklar)

Sınırlı zamanla en çok değeri veren sıra:

1. **`glossary`** — kurum kısaltmaları (tek dosya, hızlı, her aramada işe yarar)
2. **`service`** — en sık talep gelen 10 uygulama
3. **`topology`** — DMZ mobil zinciri (K2 kabul senaryosu için gerekli)
4. **`runbook`** — repo silme, erişim talebi gibi tekrar eden prosedürler
5. **`case`** — zamanla otomatik birikir (T4.3)
