from collections import Counter

from app.domain.models import RenderedImage

# Scanner noise stays well inside this, while even faint text falls outside it.
INK_CONTRAST = 64
BACKGROUND_SAMPLE_STEP = 37


def ink_ratio(image: RenderedImage) -> float:
    """Share of the page that stands out from its background, from 0.0 to 1.0.

    Measuring against the background rather than against black means a pale
    scan with faint text still counts as having content.
    """
    if not image.samples:
        return 0.0
    background = Counter(image.samples[::BACKGROUND_SAMPLE_STEP]).most_common(1)[0][0]
    is_ink = bytes(int(abs(value - background) > INK_CONTRAST) for value in range(256))
    return image.samples.translate(is_ink).count(1) / len(image.samples)
