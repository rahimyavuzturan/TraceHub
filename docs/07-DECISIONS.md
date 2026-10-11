# 07 — Karar Kaydı (ADR)

Alınan mimari kararlar, gerekçeleri ve reddedilen alternatifler.
Bir kararı değiştirmek istiyorsan mevcut kaydı **silme**; durumunu `Yerini aldı: ADR-XX`
yapıp yeni kayıt ekle.

---

## ADR-01 · Salt okunur mimari

**Durum:** Kabul edildi · 2026-09-29

**Bağlam:** Ajan prod dahil kritik sistemlere bağlanacak. Yanlış bir yazma işlemi
kesinti yaratabilir.

**Karar:** Hedef sistemlerde durum değiştiren hiçbir fonksiyon yazılmayacak.
Üç katmanlı savunma: kimlik (yetkisiz hesap), kod (fonksiyon yok + AST testi),
politika (allowlist).

**Sonuç:** Ajan sorunu düzeltemez, sadece teşhis eder ve önerir. Bu bilinçli bir
kısıttır ve projenin güvenle kullanılabilmesinin ön koşuludur.

**Reddedilen:** "Onaylı yazma işlemleri" — onay yorgunluğu gerçek bir risk;
bir kez yanlış onaylanan işlem geri alınamayabilir.

---

## ADR-02 · Fine-tune yerine RAG

**Durum:** Kabul edildi · 2026-09-29

**Bağlam:** Kurum içi GPU ve model eğitme imkânı var.

**Karar:** Fine-tune yapılmayacak. RAG + güçlü sistem promptu + araç kullanımı.

**Gerekçe:** Bu bir *bilgi* problemi, *davranış* problemi değil. Model Kubernetes'i
ve log analizini zaten biliyor; bilmediği şey bizim ortamımız. O bilgi sürekli değişir —
fine-tune edilse her değişiklikte yeniden eğitim gerekir. RAG'de bilgi eklemek =
markdown dosyası eklemek.

**Yeniden değerlendirme koşulu:** Golden testlerde araç seçimi kalıcı olarak zayıf
kalırsa, sadece *araç seçimi* için küçük bir LoRA değerlendirilebilir.

---

## ADR-03 · LangGraph ve `interrupt()` ile onay kapısı

**Durum:** Kabul edildi · 2026-09-29

**Bağlam:** Kullanıcı araştırma başlamadan önce ne yapılacağını görmek ve onaylamak istiyor.
"Her araç çağrısında onay" çok yavaş, "tam otonom" ise kontrolsüz.

**Karar:** Plan-onay modeli. Ajan önce yapılandırılmış plan üretir → kullanıcı
onaylar/düzenler/reddeder → onaylı plan içinde otonom çalışır. Plan dışına çıkmak
gerekirse tekrar onaya döner.

Teknik olarak `LangGraph.interrupt()` + checkpoint kullanılır: akış gerçekten durur,
durum veritabanına yazılır, kullanıcı saatler sonra devam ettirebilir.

**Reddedilen:**
- Her araç çağrısında onay — kullanılamaz derecede yavaş
- Risk bazlı otomatik onay — "risk" tanımı kaygan; v2'de değerlendirilebilir
- PydanticAI — onay kapısı için durum makinesini kendimiz yazmamız gerekirdi

---

## ADR-04 · MCP sunucularını kendimiz yazıyoruz

**Durum:** Kabul edildi · 2026-09-29

**Bağlam:** Hazır MCP sunucuları mevcut (Grafana, Kubernetes vb.).

**Karar:** Tüm MCP sunucuları kendimiz yazılacak, ortak bir temel katman üzerinden.

**Gerekçe:**
1. Hazır sunucular lisanslı/ücretli olabilir, kurumda kullanılamayabilir.
2. Daha önemlisi: hazır sunucular yazma araçları içerir. Salt-okunur garantisini
   *kodda* verebilmek için mutasyon fonksiyonunun hiç var olmaması gerekir.
3. Politika, redaction, audit, bütçe katmanlarını tek yerden uygulayabiliriz.

**Maliyet:** Daha fazla kod. Kabul edilebilir — araçlar ince, ortak katman kalın.

---

## ADR-05 · PostgreSQL + pgvector (tek veritabanı)

**Durum:** Kabul edildi · 2026-09-29

**Karar:** İlişkisel veri, tam metin arama (tsvector) ve vektör arama (pgvector)
tek PostgreSQL örneğinde.

**Gerekçe:** Ayrı vektör veritabanı (Qdrant/Weaviate) ikinci bir işletme yükü getirir.
Veri hacmi küçük (binlerce parça). pgvector HNSW bu ölçekte fazlasıyla yeterli.

**Yeniden değerlendirme koşulu:** Parça sayısı milyonları bulursa.

---

## ADR-06 · Hibrit arama (BM25 + vektör, RRF)

**Durum:** Kabul edildi · 2026-09-29

**Bağlam:** Kurum dili kısaltmalarla dolu: "msube", "isube", "BOA", "prep".

**Karar:** BM25 (tsvector) ve kosinüs benzerliği ayrı ayrı çalıştırılıp
Reciprocal Rank Fusion ile birleştirilecek.

**Gerekçe:** Vektör arama kurum içi kısaltmaları kaçırır (eğitim verisinde yoklar).
BM25 anlamsal eşleşmeyi kaçırır ("ödeme yapılamıyor" ↔ "payment timeout").
İkisi de şart.

---

## ADR-07 · Bilgi tabanı git'te markdown

**Durum:** Kabul edildi · 2026-09-29

**Karar:** Bilgi tabanının kaynağı `knowledge/` altındaki frontmatter'lı markdown
dosyaları. Veritabanı türetilmiş veridir.

**Gerekçe:** Versiyonlama, code review ile kalite kontrolü, kolay taşınabilirlik,
düz metin arama. Azure DevOps Wiki içeriği içe aktarılır ama kaynak burasıdır.

---

## ADR-08 · Ortam parametresi her araçta zorunlu

**Durum:** Kabul edildi · 2026-09-30

**Bağlam:** 6 mantıksal ortam, 5 cluster, 2 ELK, 2 Grafana. Yanlış ortama bakmak
yanlış teşhise yol açar.

**Karar:** Her araç çağrısında `environment` parametresi zorunlu. `config/environments.yaml`
mantıksal ortamı fiziksel hedeflere eşler. Allowlist dışı ortam reddedilir.
Prod ortamları raporda ve onay kartında görsel olarak işaretlenir.

---

## ADR-09 · Elasticsearch sorgularında zaman penceresi zorunlu

**Durum:** Kabul edildi · 2026-09-30

**Bağlam:** Kontrolsüz `_search` sorgusu üretim ELK'sini yorabilir.

**Karar:** `search_logs` ve türevlerinde zaman penceresi parametresi zorunlu
(varsayılan **60 dakika**), üst sınır politikadan (varsayılan 24 saat).
`size` üst sınırı 200. Parametresiz çağrı hata verir.

**Not:** Varsayılan 60 dakika seçildi — çoğu arıza incelemesi son bir saate bakar;
daha geniş pencere gerekiyorsa ajan açıkça istemek zorunda kalır ve bu plan onayında görünür.

---

## ADR-10 · MCP host ile ajan aynı süreçte, sunucular ayrı

**Durum:** Kabul edildi · 2026-09-30

**Karar:** MCP host katmanı FastAPI süreci içinde; MCP sunucuları geliştirmede
stdio alt süreci, üretimde ayrı pod (streamable-http).

**Gerekçe:** Üretimde her sunucu kendi kimliğiyle (ServiceAccount, ağ politikası)
çalışır — bir sunucunun ele geçirilmesi diğerlerini etkilemez. Geliştirmede
stdio ile tek komutla çalışır.

---

## ADR-11 · Faz sırası: bilgi tabanı araçlardan önce

**Durum:** Kabul edildi · 2026-09-30

**Karar:** Faz 1 (bilgi tabanı) Faz 2'den (MCP araçları) önce tamamlanacak.

**Gerekçe:**
1. Bilgi tabanı arama, ajan olmadan bile kullanılabilir bir üründür —
   "bu uygulama nerede koşuyor?" sorusunu hemen cevaplar.
2. Plan kalitesi doğrudan bilgi tabanı kalitesine bağlıdır. Araçlar önce yazılırsa
   ajan hangi namespace'e bakacağını bilemez.
3. Bilgi toplama insan zamanı gerektirir; erken başlarsa paralel ilerler.

---

## ADR-12 · Node 18+ gereksinimi

**Durum:** Açık · 2026-09-30

**Bağlam:** Geliştirme makinesinde Node 16 kurulu; Vite 5 ve modern React araçları
Node 18+ istiyor.

**Karar:** Arayüz çalışmasına (T0.5) başlamadan önce Node 18 LTS veya üstüne yükseltilecek.
Backend çalışması bundan etkilenmez, paralel ilerler.
