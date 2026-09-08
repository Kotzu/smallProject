import numpy as np
import pytest

from perfect_assassin.adapter.minimap_texture_probe import masked_texture_match


def fixture():
    rng = np.random.default_rng(3405)
    template = rng.uniform(0.15, 0.8, (12, 16))
    image = rng.uniform(0.1, 0.6, (60, 72))
    image[21:33, 31:47] = template
    return image, template, np.ones(template.shape, bool), np.ones(image.shape, bool)


def test_exact_translation():
    result = masked_texture_match(*fixture())
    assert result["status"] == "CANDIDATE_ONLY"
    assert result["offset_xy"] == [31, 21]
    assert result["similarity"] == pytest.approx(1)
    assert result["support_pixels"] == 192
    assert "floor_id" not in result


def test_brightness_and_contrast_are_not_geometry_errors():
    image, template, support, valid = fixture()
    image[21:33, 31:47] = template * 0.6 + 0.2
    result = masked_texture_match(image, template, support, valid)
    assert result["offset_xy"] == [31, 21]
    assert result["similarity"] == pytest.approx(1)


def test_transparent_pixels_do_not_contribute():
    image, template, support, valid = fixture()
    support[:, :4] = False
    template[:, :4] = 0
    result = masked_texture_match(image, template, support, valid)
    assert result["offset_xy"] == [31, 21]
    assert result["similarity"] == pytest.approx(1)


def test_invalid_roi_pixel_excludes_exact_placement():
    image, template, support, valid = fixture()
    valid[22, 32] = False
    result = masked_texture_match(image, template, support, valid)
    assert result["offset_xy"] != [31, 21]
    assert result["similarity"] < 0.5


def test_black_image_and_empty_roi_do_not_match():
    image, template, support, valid = fixture()
    assert masked_texture_match(image * 0, template, support, valid)["similarity"] is None
    assert masked_texture_match(image, template, support, valid & False)["similarity"] is None


@pytest.mark.parametrize("case", ["tiny", "constant", "too_large"])
def test_insufficient_reference(case):
    image, template, support, valid = fixture()
    if case == "tiny":
        support[:] = False
        support[:2, :2] = True
    elif case == "constant":
        template[:] = 0.5
    else:
        template = np.ones((80, 80))
        support = np.ones(template.shape, bool)
    result = masked_texture_match(image, template, support, valid)
    assert result["status"] == "INSUFFICIENT_TEXTURE"
    assert result["similarity"] is None


@pytest.mark.parametrize("value", [np.nan, np.inf, -0.01, 1.01])
def test_invalid_intensity(value):
    image, template, support, valid = fixture()
    image[0, 0] = value
    with pytest.raises(ValueError):
        masked_texture_match(image, template, support, valid)


def test_bounds_and_mask_types():
    image, template, support, valid = fixture()
    for bad in (support.astype(float), support[:, :-1]):
        with pytest.raises(ValueError):
            masked_texture_match(image, template, bad, valid)
    with pytest.raises(ValueError):
        masked_texture_match(np.zeros((513, 20)), template, support, np.ones((513, 20), bool))


def test_competing_identical_textures_remain_ambiguous():
    inputs = fixture()
    first = masked_texture_match(*inputs)
    second = masked_texture_match(*inputs)
    assert first == second
    # Correlation cannot identify which duplicated model/instance is occupied.
    assert first["status"] == "CANDIDATE_ONLY"


def test_wrong_reference_is_not_a_high_score():
    image, template, support, valid = fixture()
    wrong = np.random.default_rng(87).random(template.shape)
    assert masked_texture_match(image, wrong, support, valid)["similarity"] < 0.5


def test_non_square_fft_matches_direct_score():
    image, template, support, valid = fixture()
    image[21:33, 31:47] *= 0.7
    image[23, 33] = 1
    result = masked_texture_match(image, template, support, valid)
    x, y = result["offset_xy"]
    patch = image[y:y+template.shape[0], x:x+template.shape[1]][support]
    expected = np.corrcoef(patch, template[support])[0, 1]
    assert result["similarity"] == pytest.approx(expected, abs=1e-10)
