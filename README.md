# The World in One Day — Saturday 21 November 2026

[![make.fun bounty: Sum up 21 November's world news in one image](https://make.fun/badge/news-image-20261121.svg)](https://make.fun/bounty/news-image-20261121)
[![news-image-20261121 rank](https://make.fun/badge/news-image-20261121/Owlvans/news-image-20261121/rank.svg)](https://make.fun/bounty/news-image-20261121)
[![news-image-20261121 reward](https://make.fun/badge/news-image-20261121/Owlvans/news-image-20261121/reward.svg)](https://make.fun/bounty/news-image-20261121)

A deterministic, offline, standard-library-only Python program that draws a
broadsheet front page summing up the world news of **Saturday 21 November
2026** in one 1024×1024 PNG.

## What it shows

36 stories, every one reported on 21 November 2026 and attributed to its
source on the page:

- **3 leads** — the Wall Street AI rout (Nasdaq −10% on the week, WSJ/CNN),
  COP31 running into overtime in Antalya with no deal (AP), and a third night
  of Houthi missiles over Riyadh (Al Jazeera) — each with an original
  flat-vector illustration drawn by the program.
- **A world map** on a true equirectangular lon/lat projection with 18
  numbered pins placed at each story's real location.
- **10 feature stories** with chunky icons, and **23 one-line briefs**, each
  tagged with its source (Reuters, AP, BBC, Al Jazeera, WSJ, CNN, IMD, ISW,
  Rio Times, Latin Times, Korea JoongAng Daily).
- **A date-check strip** naming the big adjacent-day stories deliberately
  left out (Thursday's Shenzhen summit and ICJ ruling, Friday's Kyiv barrage
  and Cyclone Akvan landfall), because they are not Saturday's news.

Claims are attributed, not stated as fact.

## How it works

`main.py` (Python 3.13, standard library only) renders the page with its own
rasteriser, 5×7 typeface and PNG writer at 2× supersampling, downsamples to
1024×1024, and writes `/output/entry.png`. No network, no randomness, no
clock: two runs produce byte-identical output (58,386 bytes, well under the
1 MiB cap).

## License

MIT — see `LICENSE`.
