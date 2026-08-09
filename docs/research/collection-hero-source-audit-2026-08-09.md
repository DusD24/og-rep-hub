# Collection hero source audit — 2026-08-09

## Scope and decision rule

This audit covers the seven `research_queue` collections that did not yet have
tile media. A row passes only when its selected still is a public, receipt-linked
asset on `preview.redd.it` or `i.imgur.com`, is attributable to the recorded
author and subreddit, shows at least 80% of the intended silhouette, is a
stable JPEG/JPEG-named still, and contains no identifying text, face, or other
excluded material. Each row records the exact generic icon that must be used if
the selected asset is later removed or fails a repeat check.

| Collection | Qualifying media | Direct image URL | Post URL | Receipt ID | Author / subreddit | Provenance, privacy, and silhouette result | Fallback icon |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Balmain Anthem | yes | [JPEG](https://i.imgur.com/7RyKOIu.jpg) | [post](https://www.reddit.com/r/RepCulture_Bags/comments/1ou0bsm/the_bag_i_fell_in_love_with_that_was_not_repped/) | `ev-crawl-repculture-balmain-anthem-2025` | `u/chokemeowt` / `r/RepCulture_Bags` | The review's explicitly labeled **My Photos** Imgur album is public and author-linked from the post. The selected frame is a full front view of the black medium Anthem; it shows a hand only, with no identifying text or person, and clears the 80% silhouette threshold. | `shoulder-flap` |
| Ferragamo Hug Soft | yes | [JPEG](https://preview.redd.it/ferragamo-hug-soft-large-review-my-quiet-luxury-work-bag-of-v0-igxfxdfwtl8h1.jpg?width=1080&crop=smart&auto=webp&s=1b1c3a9eaed26b12f66d570146b2ea0398df737d) | [post](https://www.reddit.com/r/RepTherapy/comments/1ublml6/ferragamo_hug_soft_large_review_my_quiet_luxury/) | `ev-crawl-rt-ferragamo-hug-2026` (selected); `ev-crawl-rll-ferragamo-hug-2026` (supporting) | `u/soxsr` / `r/RepTherapy` | The selected public Reddit lead still belongs to the recorded in-hand review and shows the complete black-and-oxblood large Hug Soft against a plain wall. It has no identifying text or person and clears the 80% silhouette threshold. The review's linked Imgur attachment is video-only, so it is not the selected still. | `tote` |
| Saint Laurent LouLou | yes | [JPEG](https://preview.redd.it/ysl-loulou-review-v0-6m7q988vsv3h1.jpg?width=1080&crop=smart&auto=webp&s=cc95d57d376736d375f7fb00a1189f7301100588) | [post](https://www.reddit.com/r/RealRepLadies/comments/1tq3web/ysl_loulou_review/) | `ev-crawl-rll-ysl-loulou-black-frame-2026` | `u/Possible-Chip-6557` / `r/RealRepLadies` | The public Reddit lead still is the medium red LouLou described by the receipt author. It presents the front, strap, and full body on a table with no identifying text or person; the visible silhouette comfortably exceeds 80%. | `shoulder-flap` |
| Celine New Luggage | yes | [JPEG](https://i.imgur.com/V8ZcKfR.jpg) | [post](https://www.reddit.com/r/RealRepLadies/comments/1rj6c07/review_celine_new_luggage_from_baobao/) | `ev-crawl-rll-celine-new-luggage-2026` | `u/deluluvenusian` / `r/RealRepLadies` | The receipt's explicitly labeled **My photos** Imgur album is linked by its author in the public review. The selected brick medium New Luggage frame is an unobstructed full front view on bedding, with no identifying text or person, and clears the 80% silhouette threshold. | `top-handle` |
| Bottega Veneta Barbara Tote | yes | [JPEG](https://preview.redd.it/review-bv-barbara-tote-from-yuyu-v0-wsqpcirj134h1.jpg?width=1080&crop=smart&auto=webp&s=0ef2d976ad1177d5456385931fe256af6338bf32) | [post](https://www.reddit.com/r/RealRepLadies/comments/1tr2qbh/review_bv_barbara_tote_from_yuyu/) | `ev-crawl-rll-bv-barbara-medium-2026` | `u/gucci312` / `r/RealRepLadies` | The public Reddit lead still belongs to the recorded author and depicts the complete dark-brown medium woven Barbara Tote. It contains an ordinary home backdrop only, no identifying text or person, and clears the 80% silhouette threshold. | `tote` |
| Balenciaga Rodeo | yes | [JPEG](https://preview.redd.it/review-balenciaga-rodeo-from-garmen-v0-8erct48c7kjg1.jpg?width=1080&crop=smart&auto=webp&s=b11ffe43791edddd96b2dbd1eb3344d6319d8775) | [post](https://www.reddit.com/r/RealRepLadies/comments/1r51jcj/review_balenciaga_rodeo_from_garmen/) | `ev-crawl-rll-balenciaga-rodeo-medium-2026` | `u/bartsimpsonisababe` / `r/RealRepLadies` | The public Reddit lead still is an in-home photograph by the recorded review author. The medium black Rodeo is fully visible on a table; the background shopping bag is non-identifying, no person is shown, and the silhouette clears 80%. | `top-handle` |
| Chanel Slim Vanity | yes | [JPEG](https://preview.redd.it/heidi-review-chanel-vanity-slim-v0-lo3ditrgnxug1.jpeg?width=1080&crop=smart&auto=webp&s=976bca5abd3003f90007fc008fcf85ec9af2c108) | [post](https://www.reddit.com/r/RealRepLadies/comments/1sk6k8g/heidi_review_chanel_vanity_slim/) | `ev-crawl-rll-chanel-vanity-slim-2026` | `u/AudienceOk4478` / `r/RealRepLadies` | The public Reddit lead still belongs to the recorded receipt author and shows the black quilted Slim Vanity front-on. Aside from the bag's own mark, the frame has no identifying text or person and clears the 80% silhouette threshold. | `vanity` |

## Source-review notes

- The Balmain and Celine selections use public author-linked Imgur albums,
  rather than product pages or reposts. Both direct links resolve to ordinary
  JPEG stills and were visually checked frame-by-frame.
- The five selected `preview.redd.it` links are public stills embedded in their
  corresponding receipt post. Their query-string URLs follow the existing
  catalog convention for retained Reddit media.
- All selected frames are community photographs of the received item. The
  chosen source is the exact row's author/post, not a comment image or an
  unrelated post.
- Ferragamo's author-linked Imgur attachment is an MP4. The stable Reddit lead
  still is selected instead; its supporting PSP/QC receipt remains attached to
  the collection as evidence but is not used as tile media.

## Recheck policy

Before a selected image is copied into `media/evidence/`, repeat the public
availability and frame-content check against its linked receipt. If it fails,
retain the collection as `research_queue` and use the fallback icon named in
the table rather than substituting an unrelated image.
