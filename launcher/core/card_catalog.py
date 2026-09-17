"""
Card catalog and deck manager for FGO Arcade.
Parses card metadata, scans card bitmaps, and reads/writes App/deck.json.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from .config import FGOA_ROOT
CARD_DIR = os.path.join(FGOA_ROOT, "DEVICE", "print", "FGO11_AllServants")
DECK_JSON = os.path.join(FGOA_ROOT, "App", "deck.json")
NAMES_JSON = os.path.join(FGOA_ROOT, "App", "data", "CardNames.json")
EFFECTS_JSON = os.path.join(FGOA_ROOT, "App", "data", "CraftEffects.json")
MASTER_DIR = os.path.join(FGOA_ROOT, "Server", "data", "fgo-master")
PLAYERS_JSON = os.path.join(FGOA_ROOT, "Server", "state", "fgo-players.json")
AIME_TXT = os.path.join(FGOA_ROOT, "App", "aime.txt")

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
    count: int = 1
    card_info: Optional[CardInfo] = None

    def __post_init__(self):
        if self.card and not self.card_info:
            self.card_info = self.card
        elif self.card_info and not self.card:
            self.card = self.card_info

        if self.card and self.tc_id == 0:
            self.tc_id = self.card.tc_id

        if self.count != 1 and self.copies == 1:
            self.copies = self.count
        elif self.copies != 1 and self.count == 1:
            self.count = self.copies


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
        rows = {}
        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith(prefix):
                        continue
                    m = re.match(r"^" + re.escape(prefix) + r"\.(\d+)\.([^.]+)=(.*)$", line)
                    if m:
                        idx = int(m.group(1))
                        k, v = m.group(2), m.group(3)
                        if idx not in rows:
                            rows[idx] = {}
                        rows[idx][k] = v
        except Exception:
            pass
        return rows

    def _load_metadata(self):
        self.names = {}
        self.effects = {}
        if os.path.isfile(NAMES_JSON):
            try:
                with open(NAMES_JSON, "r", encoding="utf-8") as f:
                    self.names = json.load(f)
            except Exception:
                pass

        if os.path.isfile(EFFECTS_JSON):
            try:
                with open(EFFECTS_JSON, "r", encoding="utf-8") as f:
                    self.effects = json.load(f)
            except Exception:
                pass

        # 1. Servant Classes from arms_mst_svt.bin
        svt_bin = os.path.join(MASTER_DIR, "svt", "arms_mst_svt.bin")
        for d in self._parse_property_bin(svt_bin, "svt").values():
            if "svt_id" in d and "class_id" in d:
                try:
                    sid = int(d["svt_id"])
                    cid = int(d["class_id"])
                    self.svt_classes[sid] = CLASS_MAP.get(cid, f"Class {cid}")
                except ValueError:
                    pass

        # 2. Servant Rarities from arms_mst_svt_limit.bin
        limit_bin = os.path.join(MASTER_DIR, "svt", "arms_mst_svt_limit.bin")
        for d in self._parse_property_bin(limit_bin, "svt_limit").values():
            if "svt_id" in d and "rarity" in d:
                try:
                    sid = int(d["svt_id"])
                    r_str = d["rarity"].strip()
                    if sid not in self.svt_rarities:
                        self.svt_rarities[sid] = RARITY_MAP.get(r_str, 5)
                except ValueError:
                    pass

        # 3. Craft Essence Rarities from arms_mst_craft_essence.bin
        ce_bin = os.path.join(MASTER_DIR, "craft_essence", "arms_mst_craft_essence.bin")
        for d in self._parse_property_bin(ce_bin, "craft_essence").values():
            if "id" in d and "rarity" in d:
                try:
                    cid = int(d["id"])
                    r_str = d["rarity"].strip()
                    self.ce_rarities[cid] = RARITY_MAP.get(r_str, 5)
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

            tc_id = int(m.group(1))
            card_id = m.group(2)
            card_type = m.group(3)
            numeric_id = int(m.group(4))
            ascension = m.group(5)
            foil = m.group(6)
            is_holo = (foil == "HOLO" or foil == "FATAL")

            meta = self.names.get(card_id, {})
            name_en = meta.get("Chinese", card_id)  # Localization puts English into "Chinese" field
            name_jp = meta.get("Japanese", "")

            if card_type == "SVT":
                rarity = self.svt_rarities.get(numeric_id, 5)
                class_name = self.svt_classes.get(numeric_id, "Servant")
            else:
                rarity = self.ce_rarities.get(numeric_id, 5)
                class_name = "Craft Essence"

            effect_text = ""
            if card_type == "CE":
                eff = self.effects.get(card_id, {})
                effect_text = eff.get("Normal", "")

            info = CardInfo(
                filename=fn,
                card_id=card_id,
                card_type=card_type,
                name_en=name_en if name_en else card_id,
                name_jp=name_jp,
                ascension=ascension,
                is_holo=is_holo,
                effect=effect_text,
                thumbnail_path=os.path.join(CARD_DIR, fn),
                tc_id=tc_id,
                rarity=rarity,
                class_name=class_name,
            )
            self.cards.append(info)
            self.filename_to_card[fn] = info
            self.tc_to_card[tc_id] = info
            if card_id not in self.id_to_card:
                self.id_to_card[card_id] = info

    def get_all_cards(self) -> List[CardInfo]:
        return self.cards

    def get_card_by_id(self, tc_or_card_id) -> Optional[CardInfo]:
        if isinstance(tc_or_card_id, int):
            return self.tc_to_card.get(tc_or_card_id)
        if isinstance(tc_or_card_id, str):
            if tc_or_card_id.isdigit():
                return self.tc_to_card.get(int(tc_or_card_id))
            return self.id_to_card.get(tc_or_card_id)
        return None

    def get_owned_tc_ids(self) -> set:
        """Returns set of tc_ids owned by the current active player profile."""
        owned = set()
        if not os.path.isfile(PLAYERS_JSON):
            return owned

        active_access_code = None
        if os.path.isfile(AIME_TXT):
            try:
                with open(AIME_TXT, "r", encoding="utf-8") as f:
                    active_access_code = f.read().strip()
            except Exception:
                pass

        try:
            with open(PLAYERS_JSON, "r", encoding="utf-8") as f:
                players_data = json.load(f)

            target_player = None
            if active_access_code:
                for pdata in players_data.values():
                    if pdata.get("auth_access_code") == active_access_code:
                        target_player = pdata
                        break

            if not target_player and players_data:
                target_player = next(iter(players_data.values()))

            if target_player:
                counts = target_player.get("business_owned_card_counts", {})
                for tc_str, count in counts.items():
                    if count and int(count) > 0:
                        try:
                            owned.add(int(tc_str))
                        except ValueError:
                            pass
        except Exception:
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
        results = []
        q = query.lower().strip()
        tokens = q.split() if q else []
        owned_ids = self.get_owned_tc_ids() if owned_only else set()
        seen_card_ids = set()

        for c in self.cards:
            if card_type != "ALL" and c.card_type != card_type:
                continue

            if class_name != "ALL":
                if class_name == "Extra":
                    if c.class_name in ("Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker", "Craft Essence"):
                        continue
                elif c.class_name != class_name:
                    continue

            if rarity != 0 and c.rarity != rarity:
                continue

            if foil_filter == "NORMAL" and c.is_holo:
                continue
            if foil_filter == "HOLO" and not c.is_holo:
                continue

            if owned_only and c.tc_id not in owned_ids:
                continue

            if group_variants:
                if c.card_id in seen_card_ids:
                    continue
                seen_card_ids.add(c.card_id)

            if tokens:
                target_haystack = f"{c.name_en} {c.name_jp} {c.card_id} {c.class_name} {c.effect}".lower()
                if not all(tok in target_haystack for tok in tokens):
                    continue

            results.append(c)
        return results

    def load_deck(self) -> List[DeckItem]:
        items = []
        if not os.path.isfile(DECK_JSON):
            return items

        try:
            with open(DECK_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)

            cards = data.get("SelectedCards", [])
            copies = data.get("SelectedCardCopies", [])

            for idx, raw_path in enumerate(cards):
                fn = os.path.basename(raw_path.replace("\\", "/"))
                card_info = self.filename_to_card.get(fn)
                if not card_info:
                    card_info = CardInfo(
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
                items.append(DeckItem(card=card_info, copies=count, tc_id=card_info.tc_id, count=count, card_info=card_info))
        except Exception:
            pass

        return items

    def save_deck(self, deck_items: List[DeckItem]) -> bool:
        try:
            selected_cards = []
            selected_copies = []

            for item in deck_items:
                fn = item.card.filename if item.card else ""
                if not fn and item.card_info:
                    fn = item.card_info.filename
                if not fn:
                    card_obj = self.get_card_by_id(item.tc_id)
                    if card_obj:
                        fn = card_obj.filename

                if fn:
                    rel_path = f"..\\DEVICE\\print\\FGO11_AllServants\\{fn}"
                    selected_cards.append(rel_path)
                    selected_copies.append(item.copies or item.count or 1)

            data = {
                "SelectedCards": selected_cards,
                "SelectedCardCopies": selected_copies,
                "CardsPath": "../DEVICE/print/FGO11_AllServants",
            }

            with open(DECK_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False
