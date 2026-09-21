# Third-party software and services

The application's original source is licensed under **GPL-3.0-or-later**; the complete GPL version 3 text is in [LICENSE](LICENSE). Upstream projects retain their authorship and licenses. The repository does not redistribute Stockfish binaries or model weights.

| Component | Pinned/selected version | License or terms | Source and role |
| --- | --- | --- | --- |
| python-chess (`chess` on PyPI) | 1.11.2 | GPL-3.0-or-later | [Source](https://github.com/niklasf/python-chess), [license](https://github.com/niklasf/python-chess/blob/master/LICENSE.txt); legal moves, state/outcomes, PGN and UCI transport |
| Stockfish | 16; Ubuntu package 16-1build1 arm64 | GPL-3.0-or-later | [Stockfish 16 source](https://github.com/official-stockfish/Stockfish/tree/sf_16), [license](https://github.com/official-stockfish/Stockfish/blob/sf_16/Copying.txt), [Ubuntu source package](https://packages.ubuntu.com/hu/source/noble/stockfish); separate CPU engine process with NNUE evaluation |
| `@vercel/blob` | 2.7.0 | Apache-2.0 | [Source](https://github.com/vercel/storage/tree/main/packages/blob); private durable object storage SDK |
| pytest | 8.4.2 | MIT | [Source](https://github.com/pytest-dev/pytest); synthetic test runner |
| Python | Runtime version recorded per run | PSF license | [Source](https://github.com/python/cpython); worker runtime |
| Node.js | 24.x deployment runtime | MIT and bundled component notices | [Source](https://github.com/nodejs/node); public API runtime |

`package-lock.json` records resolved JavaScript dependencies and their metadata. Dependency distributions retain their own copyright and license files. The selected native engine's exact binary SHA-256 and UCI identity are saved in run records; if redistributing a compiled engine, accompany it with the matching upstream/distro source and license.

Jev is accessed as the hosted `typesafe-ai/jev` evaluation model through Vercel AI Gateway. No Jev weights are shipped here, and this application's GPL license does not grant rights to those hosted weights or alter service terms. See [TypeSafe documentation](https://docs.typesafe.ai/models) and [Vercel Gateway documentation](https://vercel.com/docs/ai-gateway/modalities/evaluation).

Chess pieces in the viewer are Unicode characters rendered with system fonts. No third-party chess artwork or downloadable font files are bundled.
