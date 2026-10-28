from pocket_cart.cart import Cart


def test_adding_twice_adds_quantity():
    cart = Cart()
    cart.add("TEE", 1, 2000)
    cart.add("TEE", 2, 2000)
    assert cart.total_cents() == 6000


def test_remove_missing_sku_is_quiet():
    Cart().remove("NOPE")


def test_two_lines():
    cart = Cart()
    cart.add("TEE", 1, 2000)
    cart.add("SOCK", 2, 500)
    assert cart.total_cents() == 3000
