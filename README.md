# HubTube â€” GitHub-only Technology Benefit Radar

HubTube, Tokenoskobi ve Quant Simulator iÃ§in salt-okunur, artÄ±mlÄ± teknoloji radarÄ±
Ã§ekirdeÄŸidir. Ä°sim, GitHub keÅŸfini ve ileride eklenecek YouTube katmanÄ±nÄ± birleÅŸtirir.

Bu sÃ¼rÃ¼m mimari sÃ¶zleÅŸmeyi dondurur ve aÅŸaÄŸÄ±daki temelleri saÄŸlar:

- SQLite ÅŸemasÄ± ve append-only olay geÃ§miÅŸi
- aday durumu + olay geÃ§miÅŸinin tek transaction iÃ§inde gÃ¼ncellenmesi
- idempotent iÅŸ sonucu kaydÄ±
- source/content/analysis kimlikleri
- checkpoint ve overlap modeli
- politika kapÄ±larÄ± iÃ§in kayÄ±t modeli
- impact ve confidence skorlarÄ±nÄ±n ayrÄ± tutulmasÄ±
- boÅŸ sonuÃ§larÄ± da destekleyen gÃ¼nlÃ¼k Markdown raporu
- salt-okunur Repository Observer v1

## HÄ±zlÄ± baÅŸlangÄ±Ã§

Python 3.11 veya Ã¼zeri yeterlidir; harici paket gerekmez.

```powershell
python -m radar --db work/radar.db init
python -m radar --db work/radar.db self-test
python -m radar --db work/radar.db report --date 2026-08-01 --output work/daily-report.md
python -m radar observe C:\path\to\repository --output work\snapshot.json
```

Observer yalnÄ±z dosya okur; kod Ã§alÄ±ÅŸtÄ±rmaz ve paket kurmaz. `.git`, sanal ortamlar,
`node_modules` ve cache dizinlerini atlar. Dosya hash'leri, sÄ±nÄ±flandÄ±rma, hassas dosya
iÅŸaretleri ve Python import iliÅŸkileri Ã¼retir. Hassas dosyalarÄ±n iÃ§eriÄŸi Ã§Ä±ktÄ±ya yazÄ±lmaz.

GerÃ§ek GitHub taramasÄ±ndan Ã¶nce `config.example.toml` dosyasÄ±nÄ± `config.toml` olarak
kopyalayÄ±n ve iki repository deÄŸerini doldurun. Token gerekiyorsa yalnÄ±z ortam
deÄŸiÅŸkeninden verilmelidir; yapÄ±landÄ±rma veya veritabanÄ±na yazÄ±lmamalÄ±dÄ±r.

```powershell
$env:RADAR_GITHUB_TOKEN = "..."
python -m radar --db work/radar.db scan-github --config config.toml
```

`scan-github` bu baÅŸlangÄ±Ã§ sÃ¼rÃ¼mÃ¼nde bilinÃ§li olarak devre dÄ±ÅŸÄ±dÄ±r; repo adresleri
doÄŸrulandÄ±ktan sonra GitHub istemcisi eklenmelidir. HiÃ§bir komut hedef repolara yazmaz.

## Belgeler

- `docs/TECHNICAL_SPEC_v1.md`: dondurulmuÅŸ uygulama sÃ¶zleÅŸmesi
- `schema/001_initial.sql`: SQLite veri modeli ve invariant trigger'larÄ±
- `config.example.toml`: Ã§alÄ±ÅŸma politikasÄ± Ã¶rneÄŸi

## Lisans

MIT
