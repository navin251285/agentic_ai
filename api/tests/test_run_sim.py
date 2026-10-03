import argparse

import pytest

from app import run_sim


def test_parse_order():
    assert run_sim.parse_order("cold-drink:20@30.5") == run_sim.ManualOrder("cold-drink", 20, 30.5)
    for bad in ["milk:20", "milk@30", "milk:0@30", "Milk:2@3"]:
        with pytest.raises(argparse.ArgumentTypeError):
            run_sim.parse_order(bad)


def test_fast_run_with_manual_order(capsys):
    code = run_sim.main(["--fast", "--no-agent", "--duration", "100", "--seed", "1", "--order", "milk:20@30"])
    out = capsys.readouterr().out
    assert code == 0
    placed = [line for line in out.splitlines() if "ORDER_PLACED" in line]
    assert len(placed) == 1 and placed[0].lstrip().startswith("30.0") and "O-0001" in placed[0]
    assert "DELIVERED" in out and "orders placed 1" in out and "seed 1" in out


def test_fast_run_is_reproducible(capsys):
    args = ["--fast", "--speed", "5", "--duration", "120", "--seed", "3", "--quiet"]
    run_sim.main(args)
    first = capsys.readouterr().out
    run_sim.main(args)
    second = capsys.readouterr().out
    strip = lambda s: [ln for ln in s.splitlines() if "ticks in" not in ln]  # noqa: E731
    assert strip(first) == strip(second)


def test_unknown_product_in_order_fails(capsys):
    assert run_sim.main(["--fast", "--duration", "1", "--order", "nope:1@0"]) == 2
