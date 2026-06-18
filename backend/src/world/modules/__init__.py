"""Tier 1 — the latent modules, each a self-contained sealed box.

A module owns its hidden state, its kernel, its noiseless emission, its
display vocabulary, and its data tables. It imports ONLY the global config
and its own files -- NEVER a sibling module (transition + observation
independence => the joint belief stays a product of marginals, Becker
Def. 2). registry.py composes the modules into Module records; the modules
never import registry (the one-way edge that breaks the cycle)."""
