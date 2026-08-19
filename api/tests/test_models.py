import pytest
from pydantic import ValidationError

from app.models import Ingredient, ProductIn, ProductType, Unit


def test_amount_without_unit_is_rejected():
    with pytest.raises(ValidationError, match="needs a unit"):
        Ingredient(name="sodium benzoate", amount=0.08)


def test_amount_with_unit_is_accepted():
    ingredient = Ingredient(name="sodium benzoate", amount=0.08, unit=Unit.PERCENT_W_W)
    assert ingredient.unit is Unit.PERCENT_W_W


def test_ingredient_without_amount_needs_no_unit():
    assert Ingredient(name="ginger").unit is None


def test_product_type_is_an_enum_not_free_text():
    with pytest.raises(ValidationError):
        ProductIn(name="X", product_type="herbal drink", origin="ID")


def test_origin_must_be_a_two_letter_code():
    with pytest.raises(ValidationError):
        ProductIn(name="X", product_type=ProductType.FOOD_BEVERAGE_POWDER, origin="Indonesia")
