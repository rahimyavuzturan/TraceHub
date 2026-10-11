# 01 — Proje Planı

## 1. Problem

DevOps ekibine her gün çok sayıda talep geliyor:

- "**** uygulamasında arıza var, bakabilir misiniz?"
- "**** reposunu Azure DevOps'tan silebilir miyiz?"
- "Şu servisin logları nerede?"
- "DMZ BOA'nın prep mobilinde arıza var."

Bu taleplerin çözümünde zamanın büyük kısmı **sorunu bulmaya** değil, **nerede bakacağını
bulmaya** gidiyor:

1. Talepte geçen "uygulama adı" resmi bir isim değil, kullanıcının bildiği isim.
   Hangi repo, hangi cluster, hangi namespace, hangi ELK index'i, hangi NLB vserver'ı
   olduğunu bilmek gerekiyor.
2. Bu bilgi ekibin kafasında ve dağınık notlarda duruyor. Yeni gelen kişi bunu bilmiyor,
   bilen kişi de her seferinde aynı keşfi tekrar yapıyor.
3. Arıza analizi çok katmanlı: NLB → web sunucusu → entegrasyon katmanı → backend.
   Her katmanda ayrı bir arayüz, ayrı bir kimlik, ayrı bir sorgu dili var.

### Gerçek vaka (referans senaryo)

> "DMZ BOA'nın prep mobilinde arıza var."

Manuel olarak yapılan adımlar:

1. Citrix NLB'de "mobil" araması → prep olanı seç
2. Member IP'lerini al, DNS çözümlerine bak
3. Makineye bağlan, logları incele → sorun yok
4. Integration'ın ulaştığı backend sunucularına geç
5. Onları kontrol et → **sorun burada**
6. Logları analiz et
7. İlgili ekiple görüş

Bu zinciri bir ajanın takip etmesi hedefleniyor.

---

## 2. Hedef

TraceHub şunu yapar:

| Girdi | Çıktı |
|---|---|
| Serbest metin talep ("prep mobilde arıza var") | Yapılandırılmış araştırma planı → onay → kanıtlı rapor |
| "Bu repo nerede?" | Bilgi tabanından cevap + link |
| "Bu repoyu silebilir miyiz?" | Prosedür + gereken onaylar + uyarılar + adım adım yol |

TraceHub şunu **yapmaz**:

- Hiçbir sistemde değişiklik yapmaz (pod restart, config değişikliği, repo silme...).
- Kullanıcı yerine karar vermez; öneri sunar, kanıt gösterir, uyarır.

---

## 3. Kapsam

### 3.1 MVP kapsamı (v1)

- Web arayüzü: chat, plan onayı, canlı araştırma izi, rapor
- Bilgi tabanı: markdown + pgvector hibrit arama
- Salt-okunur MCP araçları: **Kubernetes/Rancher**, **Elasticsearch/ELK**, **Grafana**
- LangGraph orkestrasyonu: plan üret → onay al → araştır → raporla
- Vaka hafızası: çözülen vakalar bilgi tabanına geri yazılır
- Basit yerel kimlik doğrulama (küçük DevOps ekibi)
- Audit: her araç çağrısı kaydedilir

### 3.2 v1.1 kapsamı

- WinRM (JEA) salt-okunur araçları
- Citrix NetScaler NITRO salt-okunur araçları
- Azure DevOps salt-okunur araçları
- Çok katmanlı zincir takibi (topoloji grafiği yürütücü)

### 3.3 Kapsam dışı (bilerek)

| Özellik | Neden |
|---|---|
| Otomatik düzeltme / remediation | Altın kural: salt okunur |
| Mail / Mercek'ten otomatik ticket çekme | MVP'de talep elle yapıştırılıyor; entegrasyon karmaşıklığı erken risk |
| Teams / Slack botu | Arayüz önce olgunlaşmalı |
| Model fine-tune | RAG + prompt yeterli; wiki değişince model bayatlar |
| LDAP / AD entegrasyonu | Küçük ekip, yerel auth yeterli |
| RDP ekran görüntüsü analizi | Kırılgan, otomatikleştirmesi zor; WinRM yeterli |

Bunlardan biri isteniyorsa **önce bu doküman ve AGENTS.md güncellenir**, sonra kod yazılır.

---

## 4. Başarı Kriterleri

MVP'nin "çalışıyor" sayılması için:

### K1 — CrashLoopBackOff kök neden analizi

Girdi: *"prod'da ödeme servisi ayağa kalkmıyor"*

Beklenen davranış:

1. Bilgi tabanından "ödeme servisi" → cluster + namespace + deployment eşleşmesi
2. Plan üretir: pod listesi → describe → önceki container logları → ES hata kümesi
3. Onay sonrası bu sorguları otonom yürütür
4. Rapor: kök neden hipotezi (ör. config map eksik anahtar) + kanıt olarak log satırı +
   önerilen adım + gereken onay uyarısı

### K2 — Çok katmanlı zincir takibi (DMZ prep mobil)

Girdi: *"DMZ BOA prep mobilde arıza var"*

Beklenen davranış:

1. Bilgi tabanından topoloji: NLB vserver → web katmanı → integration → backend
2. Plan: katman katman sağlık kontrolü
3. Zinciri sırayla yürütür, sağlıklı katmanı eler, bozuk katmanda derinleşir
4. Rapor: "sorun backend katmanında, şu hata şu sunucuda şu saatte başladı" + kanıt

### K3 — Bilgi tabanı sorgusu

Girdi: *"**** reposunu silebilir miyiz?"*

Beklenen davranış: Repo konumu + silme prosedürü + gereken onaylar + uyarılar,
araç çağrısına gerek kalmadan (veya tek bir Azure DevOps okuma çağrısıyla).

### K4 — Güvenlik değişmezi

- `pytest` içindeki AST testi, MCP paketlerinde mutasyon fonksiyonu olmadığını kanıtlar.
- Salt-okunur servis hesabıyla mutasyon denemesi 403 döner (negatif test).
- Audit tablosunda her araç çağrısı kim/ne zaman/hangi ortam/hangi parametre olarak bulunur.

---

## 5. Kullanıcı ve Ortamlar

- **Kullanıcı**: küçük DevOps ekibi (basit yerel kimlik doğrulama)
- **Ortamlar**: prod, preprod, test — ve her birinin DMZ karşılığı
- **Altyapı**: 5 Kubernetes cluster, 20+ namespace, 2 ELK, 2 Grafana (prod/test)
- **Ağ**: on-prem, kısıtlı internet (proxy üzerinden paket indirilebilir)
- **LLM**: kurum içi GPU üzerinde vLLM

---

## 6. Yol Haritası (özet)

| Faz | İçerik | Bağımlılık |
|---|---|---|
| Faz 0 | Monorepo iskeleti, config, DB, LLM istemcisi, UI iskeleti | — |
| **Faz 1** | **Bilgi tabanı** (şema, ingest, hibrit arama, toplama asistanı) | Faz 0 |
| Faz 2 | MCP ortak katmanı + Kubernetes + Elasticsearch araçları | Faz 0 |
| Faz 3 | LangGraph orkestrasyonu + plan-onay kapısı + rapor | Faz 1, 2 |
| Faz 4 | K1 kabul senaryosu, golden test harness, vaka hafızası | Faz 3 |
| Faz 5 | Grafana, WinRM, NetScaler, Azure DevOps + K2 senaryosu | Faz 4 |
| Faz 6 | Auth, sır yönetimi, Helm, gözlemlenebilirlik | Faz 4 |

**Faz 1 neden önce?** Bilgi tabanı arama, ajan olmadan bile değerlidir: "bu uygulama nerede
koşuyor?" sorusunu cevaplayan bir arama aracı ilk somut kazanımdır. Ayrıca Faz 3'teki
planlama kalitesi doğrudan bilgi tabanının kalitesine bağlıdır.

Detaylı görev listesi: [04-WORK-BREAKDOWN.md](04-WORK-BREAKDOWN.md)

---

## 7. Riskler

| Risk | Etki | Azaltma |
|---|---|---|
| Bilgi tabanı boş/eksik kalır → ajan kör | Yüksek | T1.5 "ham metin → markdown" asistanı ile toplama kolaylaştırılır; T1.6 AzDO Wiki içe aktarımı |
| Yerel modelin araç seçimi zayıf | Yüksek | Araç sayısı sınırlı tutulur, docstring'ler Türkçe ve net, golden test ile ölçülür |
| Kontrolsüz ES sorgusu cluster'ı yorar | Orta | Zorunlu zaman penceresi + boyut limiti + sorgu bütçesi |
| WinRM/JEA için güvenlik onayı gecikir | Orta | Faz 5'e konuldu; talep erken açılır |
| Salt-okunur ihlali | Kritik | Üç katmanlı savunma + AST invariant testi ([06-SECURITY.md](06-SECURITY.md)) |
| Tek kişilik geliştirme, bağlam kaybı | Orta | Görevler küçük ve bağımsız; [08-STATUS.md](08-STATUS.md) her oturumda güncellenir |
