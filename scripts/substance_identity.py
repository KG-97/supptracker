"""Conservative identity rules for openFDA compound identifiers."""

from __future__ import annotations

import re
import unicodedata

SALT_HYDRATE_ESTER_WORDS = frozenset(
    """
    acetate acetonide adipate aspartate benzoate besylate bisulfate bitartrate
    bromide calcium carbonate chloride citrate dihydrate dihydrochloride disodium
    edetate ethylsuccinate fumarate gluconate hcl hemihydrate hydrate hydrobromide
    hydrochloride hyclate lactate maleate mesylate monohydrate nitrate olamine
    oxalate phosphate potassium sodium succinate sulfate sulphate tartrate
    tosylate trihydrate valerate
    """.split()
)
FORM_WORDS = frozenset(
    """
    anhydrous capsule capsules delayed dr er extended gel injection light
    macrocrystals mg oral otic release ring solution suspension system tablet
    tablets topical transdermal vaginal
    """.split()
)
BIOLOGIC_SUFFIXES = frozenset({"aeeb", "leyk"})
TRAILING_PHRASES = frozenset(
    {
        ("benzalkonium", "chloride"),
        ("propanediol",),
    }
)

# These openFDA identifiers flatten comma-separated ingredients, so their
# component boundary is not represented by "-and-".  Keep this short,
# explicit list instead of guessing from a shared first token.
FLATTENED_COMBINATIONS = {
    "brompheniramine-maleate-pseudoephedrine-hydrochloride-and-dextromethorphan-hydrobromide": (
        "brompheniramine-maleate",
        "pseudoephedrine-hydrochloride",
        "dextromethorphan-hydrobromide",
    ),
    "brompheniramine-pseudoephedrine-dextromethorphan": (
        "brompheniramine",
        "pseudoephedrine",
        "dextromethorphan",
    ),
    "butalbital-acetaminophen-and-caffeine": (
        "butalbital",
        "acetaminophen",
        "caffeine",
    ),
    "dextrose-monohydrate-sodium-chloride-sodium-lactate-potassium-chloride-calcium-chloride": (
        "dextrose-monohydrate",
        "sodium-chloride",
        "sodium-lactate",
        "potassium-chloride",
        "calcium-chloride",
    ),
    "diclofenac-sodium-capsaicin": (
        "diclofenac-sodium",
        "capsaicin",
    ),
    "dorzolamide-hydrochloride-timolol-maleate": (
        "dorzolamide-hydrochloride",
        "timolol-maleate",
    ),
    "olmesartan-medoxomil-hydrochlorothiazide": (
        "olmesartan-medoxomil",
        "hydrochlorothiazide",
    ),
}


def _tokens(value: str) -> tuple[str, ...]:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return tuple(re.findall(r"[a-z0-9]+", ascii_value.lower()))


def _base_tokens(value: str) -> tuple[str, ...]:
    tokens = list(_tokens(value))
    while tokens:
        phrase = next(
            (
                candidate
                for candidate in TRAILING_PHRASES
                if len(tokens) >= len(candidate) and tuple(tokens[-len(candidate):]) == candidate
            ),
            None,
        )
        if phrase is not None:
            del tokens[-len(phrase):]
        elif (
            tokens[-1] in SALT_HYDRATE_ESTER_WORDS
            or tokens[-1] in FORM_WORDS
            or tokens[-1] in BIOLOGIC_SUFFIXES
            or tokens[-1].isdigit()
        ):
            tokens.pop()
        else:
            break
    return tuple(tokens)


def _ingredient_bases(value: str) -> set[tuple[str, ...]]:
    identifier = "-".join(_tokens(value))
    if not identifier:
        return set()

    bases = {_base_tokens(identifier)}
    if identifier in FLATTENED_COMBINATIONS:
        bases.update(_base_tokens(ingredient) for ingredient in FLATTENED_COMBINATIONS[identifier])
    elif "-and-" in identifier:
        bases.update(_base_tokens(ingredient) for ingredient in identifier.split("-and-"))
    elif "-with-" in identifier:
        bases.update(_base_tokens(ingredient) for ingredient in identifier.split("-with-"))
    elif "-in-" in identifier:
        bases.update(_base_tokens(ingredient) for ingredient in identifier.split("-in-"))
    return {base for base in bases if base}


def is_same_substance(compound_a: str, compound_b: str) -> bool:
    """Return whether two openFDA identifiers denote the same active substance.

    The rule removes only terminal salt, hydrate, ester, dosage-form, and known
    biologic-suffix words, then compares the complete remaining token sequence.
    It also recognises explicit combination separators and the small set of
    corpus identifiers whose flattened ingredients have no separator; it never
    compares a first token or arbitrary prefix.
    """
    return bool(_ingredient_bases(compound_a) & _ingredient_bases(compound_b))
