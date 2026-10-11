# TraceHub

**Salt okunur DevOps teşhis asistanı.**

DevOps ekibine gelen günlük talepleri ("X uygulamasında arıza var", "Y reposunu silebilir miyiz?")
alır; kurum içi bilgi arşivi (RAG) ve salt-okunur sistem entegrasyonlarını kullanarak sorunu
kendi kendine araştırır; **hiçbir değişiklik yapmadan** kök neden analizi ve adım adım eylem
önerisi sunar.

```
Talep → Normalize → Bilgi tabanı araması → PLAN ÜRET → [KULLANICI ONAYI] →
  Onaylı plan içinde otonom araştırma (salt-okunur araçlar) → Kanıtlı rapor → Vaka hafızası
```

---

## Dokümantasyon

Kod yazmadan önce ilgili dokümanı oku.

| Doküman | İçerik |
|---|---|
| [AGENTS.md](AGENTS.md) | **Kod yazan ajanlar için zorunlu okuma.** Altın kural, kodlama standartları, MCP şablonu |
| [docs/01-PROJECT-PLAN.md](docs/01-PROJECT-PLAN.md) | Problem, hedefler, kapsam, başarı kriterleri, kullanım senaryoları |
| [docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) | Katmanlar, veri akışı, dizin yapısı, veritabanı şeması |
| [docs/03-TECH-STACK.md](docs/03-TECH-STACK.md) | Teknoloji seçimleri ve gerekçeleri |
| [docs/04-WORK-BREAKDOWN.md](docs/04-WORK-BREAKDOWN.md) | Faz ve görev kırılımı, bağımlılıklar, kabul kriterleri |
| [docs/05-KNOWLEDGE-BASE.md](docs/05-KNOWLEDGE-BASE.md) | Bilgi tabanı şeması, frontmatter spesifikasyonu, yazım rehberi |
| [docs/06-SECURITY.md](docs/06-SECURITY.md) | Salt-okunur savunma katmanları, servis hesapları, sır yönetimi |
| [docs/07-DECISIONS.md](docs/07-DECISIONS.md) | Alınan kararlar ve gerekçeleri (ADR kaydı) |
| [docs/08-STATUS.md](docs/08-STATUS.md) | **Güncel ilerleme durumu.** Oturuma başlarken önce buraya bak |

---

## Altın Kural

TraceHub hedef sistemlerde **asla** değişiklik yapmaz. Durum değiştiren fonksiyon
*yazılmaz* — yazılmadığı için yanlışlıkla çağrılması da mümkün olmaz.
Detay: [docs/06-SECURITY.md](docs/06-SECURITY.md)

---

## Hızlı Başlangıç

```powershell
# 1. Veritabani
docker compose up -d

# 2. Python ortami
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 3. Ayarlar
Copy-Item .env.example .env    # duzenle

# 4. Dogrula
pytest -q
```

Gereksinimler: Python 3.12+, Docker, (arayüz için) Node 18+.

---

## Durum

Proje planlama aşamasını tamamladı, geliştirme Faz 0'dan başlıyor.
Güncel durum için [docs/08-STATUS.md](docs/08-STATUS.md).
