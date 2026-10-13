"""
Card catalog and deck manager for FGO Arcade.
Parses card metadata, scans card bitmaps, and reads/writes App/deck.json.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from launcher.core.config import APP_DIR, CARD_DIR, DECK_FILE as DECK_JSON, SERVER_DIR

NAMES_JSON = os.path.join(APP_DIR, "data", "CardNames.json")
EFFECTS_JSON = os.path.join(APP_DIR, "data", "CraftEffects.json")
MASTER_DIR = os.path.join(SERVER_DIR, "data", "fgo-master")
PLAYERS_JSON = os.path.join(SERVER_DIR, "state", "fgo-players.json")
AIME_TXT = os.path.join(APP_DIR, "aime.txt")

CLASS_MAP = {
    1: "Saber",
    2: "Archer",
    3: "Lancer",
    4: "Rider",
    5: "Caster",
    6: "Assassin",
    7: "Berserker",
    8: "Shielder",
    9: "Ruler",
    10: "Alter Ego",
    11: "Avenger",
    23: "Moon Cancer",
    25: "Foreigner",
    26: "Beast",
}

RARITY_MAP = {
    "COMMON": 1,
    "UNCOMMON": 2,
    "RARE": 3,
    "SRARE": 4,
    "SSRARE": 5,
}


def _read_json(path: str, default):
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


@dataclass
class CardInfo:
    filename: str
    card_id: str
    card_type: str  # "SVT" or "CE"
    name_en: str
    name_jp: str
    ascension: str
    is_holo: bool
    effect: str = ""
    thumbnail_path: str = ""
    tc_id: int = 0
    rarity: int = 5
    class_name: str = ""

    @property
    def image_path(self) -> str:
        return self.thumbnail_path


@dataclass
class DeckItem:
    card: Optional[CardInfo] = None
    copies: int = 1
    tc_id: int = 0

    def __post_init__(self):
        if self.card and not self.tc_id:
            self.tc_id = self.card.tc_id


class CardCatalog:
    def __init__(self):
        self.cards: List[CardInfo] = []
        self.id_to_card: Dict[str, CardInfo] = {}
        self.tc_to_card: Dict[int, CardInfo] = {}
        self.filename_to_card: Dict[str, CardInfo] = {}
        self.svt_classes: Dict[int, str] = {}
        self.svt_rarities: Dict[int, int] = {}
        self.ce_rarities: Dict[int, int] = {}
        self._load_metadata()
        self._scan_cards()

    def _parse_property_bin(self, file_path: str, prefix: str) -> Dict[int, Dict[str, str]]:
        if not os.path.isfile(file_path):
            return {}
        rows: Dict[int, Dict[str, str]] = {}
        pat = re.compile(rf"^{re.escape(prefix)}\.(\d+)\.([^.]+)=(.*)$")
        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    if m := pat.match(line.strip()):
                        rows.setdefault(int(m.group(1)), {})[m.group(2)] = m.group(3)
        except Exception:
            pass
        return rows

    def _load_metadata(self):
        self.names = _read_json(NAMES_JSON, {})
        self.effects = _read_json(EFFECTS_JSON, {})

        # 1. Servant Classes from arms_mst_svt.bin
        svt_bin = os.path.join(MASTER_DIR, "svt", "arms_mst_svt.bin")
        for d in self._parse_property_bin(svt_bin, "svt").values():
            if "svt_id" in d and "class_id" in d:
                try:
                    cid = int(d["class_id"])
                    self.svt_classes[int(d["svt_id"])] = CLASS_MAP.get(cid, f"Class {cid}")
                except ValueError:
                    pass

        # 2. Servant Rarities from arms_mst_svt_limit.bin
        limit_bin = os.path.join(MASTER_DIR, "svt", "arms_mst_svt_limit.bin")
        for d in self._parse_property_bin(limit_bin, "svt_limit").values():
            if "svt_id" in d and "rarity" in d:
                try:
                    self.svt_rarities.setdefault(int(d["svt_id"]), RARITY_MAP.get(d["rarity"].strip(), 5))
                except ValueError:
                    pass

        # 3. Craft Essence Rarities from arms_mst_craft_essence.bin
        ce_bin = os.path.join(MASTER_DIR, "craft_essence", "arms_mst_craft_essence.bin")
        for d in self._parse_property_bin(ce_bin, "craft_essence").values():
            if "id" in d and "rarity" in d:
                try:
                    self.ce_rarities[int(d["id"])] = RARITY_MAP.get(d["rarity"].strip(), 5)
                except ValueError:
                    pass

    def _scan_cards(self):
        if not os.path.isdir(CARD_DIR):
            return

        pattern = re.compile(r"^(\d+)_((SVT|CE)(\d+))_(A\d+)_([A-Z]+)\.bmp$")
        for fn in sorted(os.listdir(CARD_DIR)):
            m = pattern.match(fn)
            if not m:
                continue

            tc_id, card_id, card_type, numeric_id, ascension, foil = (
                int(m.group(1)),
                m.group(2),
                m.group(3),
                int(m.group(4)),
                m.group(5),
                m.group(6),
            )
            meta = self.names.get(card_id, {})
            if card_type == "SVT":
                rarity = self.svt_rarities.get(numeric_id, 5)
                class_name = self.svt_classes.get(numeric_id, "Servant")
                effect_text = ""
            else:
                rarity = self.ce_rarities.get(numeric_id, 5)
                class_name = "Craft Essence"
                effect_text = self.effects.get(card_id, {}).get("Normal", "")

            info = CardInfo(
                filename=fn,
                card_id=card_id,
                card_type=card_type,
                name_en=meta.get("Chinese") or card_id,  # Localization puts English into "Chinese" field
                name_jp=meta.get("Japanese", ""),
                ascension=ascension,
                is_holo=foil in ("HOLO", "FATAL"),
                effect=effect_text,
                thumbnail_path=os.path.join(CARD_DIR, fn),
                tc_id=tc_id,
                rarity=rarity,
                class_name=class_name,
            )
            self.cards.append(info)
            self.filename_to_card[fn] = info
            self.tc_to_card[tc_id] = info
            self.id_to_card.setdefault(card_id, info)

    def get_all_cards(self) -> List[CardInfo]:
        return self.cards

    def get_card_by_id(self, tc_or_card_id) -> Optional[CardInfo]:
        if isinstance(tc_or_card_id, int):
            return self.tc_to_card.get(tc_or_card_id)
        if isinstance(tc_or_card_id, str):
            return self.tc_to_card.get(int(tc_or_card_id)) if tc_or_card_id.isdigit() else self.id_to_card.get(tc_or_card_id)
        return None

    def get_owned_tc_ids(self) -> set:
        """Returns set of tc_ids owned by the current active player profile."""
        players_data = _read_json(PLAYERS_JSON, {})
        if not players_data:
            return set()

        active_code = ""
        if os.path.isfile(AIME_TXT):
            try:
                with open(AIME_TXT, "r", encoding="utf-8") as f:
                    active_code = f.read().strip()
            except Exception:
                pass

        target_player = next(
            (p for p in players_data.values() if active_code and p.get("auth_access_code") == active_code),
            next(iter(players_data.values()), None),
        )
        if not target_player:
            return set()

        owned = set()
        for tc_str, count in target_player.get("business_owned_card_counts", {}).items():
            try:
                if count and int(count) > 0:
                    owned.add(int(tc_str))
            except ValueError:
                pass
        return owned

    def search(
        self,
        query: str = "",
        card_type: str = "ALL",
        class_name: str = "ALL",
        rarity: int = 0,
        foil_filter: str = "ALL",
        owned_only: bool = False,
        group_variants: bool = False,
    ) -> List[CardInfo]:
        tokens = query.lower().split()
        owned_ids = self.get_owned_tc_ids() if owned_only else set()
        seen_card_ids = set()
        std_classes = ("Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker", "Craft Essence")
        results = []

        for c in self.cards:
            if card_type != "ALL" and c.card_type != card_type:
                continue
            if class_name != "ALL":
                if (class_name == "Extra" and c.class_name in std_classes) or (class_name != "Extra" and c.class_name != class_name):
                    continue
            if rarity != 0 and c.rarity != rarity:
                continue
            if (foil_filter == "NORMAL" and c.is_holo) or (foil_filter == "HOLO" and not c.is_holo):
                continue
            if owned_only and c.tc_id not in owned_ids:
                continue
            if group_variants:
                if c.card_id in seen_card_ids:
                    continue
                seen_card_ids.add(c.card_id)
            if tokens:
                haystack = f"{c.name_en} {c.name_jp} {c.card_id} {c.class_name} {c.effect}".lower()
                if not all(tok in haystack for tok in tokens):
                    continue
            results.append(c)
        return results

    def load_deck(self) -> List[DeckItem]:
        data = _read_json(DECK_JSON, {})
        cards = data.get("SelectedCards", [])
        copies = data.get("SelectedCardCopies", [])
        items = []

        for idx, raw_path in enumerate(cards):
            fn = os.path.basename(raw_path.replace("\\", "/"))
            card_info = self.filename_to_card.get(fn) or CardInfo(
                filename=fn,
                card_id=fn,
                card_type="SVT" if "SVT" in fn else "CE",
                name_en=fn,
                name_jp="",
                ascension="",
                is_holo="HOLO" in fn,
                thumbnail_path=os.path.join(CARD_DIR, fn),
            )
            count = copies[idx] if idx < len(copies) else 1
            items.append(DeckItem(card=card_info, copies=count, tc_id=card_info.tc_id))
        return items

    def save_deck(self, deck_items: List[DeckItem]) -> bool:
        try:
            rel_folder = os.path.basename(CARD_DIR)
            selected_cards, selected_copies = [], []
            for item in deck_items:
                card_obj = item.card or self.get_card_by_id(item.tc_id)
                if card_obj and card_obj.filename:
                    selected_cards.append(f"..\\DEVICE\\print\\{rel_folder}\\{card_obj.filename}")
                    selected_copies.append(item.copies or 1)

            data = {
                "SelectedCards": selected_cards,
                "SelectedCardCopies": selected_copies,
                "CardsPath": f"../DEVICE/print/{rel_folder}",
            }
            with open(DECK_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False
