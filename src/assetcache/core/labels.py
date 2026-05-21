"""Label vocabulary — seed data and the runtime registry.

The single source of truth for the label vocabulary is the ``labels``
SQLite table.  ``SEED_LABELS`` below is just the bootstrap content
loaded once into an empty DB; after that, users can add / disable /
edit labels through the GUI (M2.6 labels-admin dialog).

24 axes ≈ 316 seed labels:
  * 14 visual axes (CLIP-scored): category / style / mood / palette /
    color / view / material / lighting / time_of_day / weather / theme /
    size_hint / domain / animation
  * 10 sound axes (Gemma-only): sound_category / sound_mood /
    sound_timbre / sound_environment / sound_instrument / sound_tempo /
    sound_intensity / sound_use / sound_genre / sound_voice_type

Every seed entry carries an English one-sentence description used by
the FTS5 builder and exposed via the future MCP ``describe_label``
tool — Claude Code reads these to map natural-language queries onto
the label vocabulary.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .store import LabelRow, Store


# ── 라벨 토큰 검증 ──────────────────────────────────────────────────


# 영문 소문자 시작 + 알파벳·숫자·`_` 허용, 최대 32자.
_LABEL_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class LabelValidationError(ValueError):
    """Raised when a label token doesn't match the registry's lexical rules."""


def _validate_token(token: str) -> None:
    if not isinstance(token, str) or not _LABEL_TOKEN_RE.fullmatch(token):
        raise LabelValidationError(
            f"label token {token!r} must match ^[a-z][a-z0-9_]{{0,31}}$"
        )


# ── 시드 (label, description) 튜플로 박는다 ─────────────────────────


SEED_LABELS: dict[str, list[tuple[str, str]]] = {
    # ── 시각: 무엇/누구 ──────────────────────────────────────────────
    "category": [
        ("character",   "Animate or anthropomorphic entity such as a hero, enemy, or NPC."),
        ("creature",    "Non-humanoid living being: monster, animal, beast, alien."),
        ("tile",        "Repeatable terrain or floor block used for level construction."),
        ("background",  "Backdrop or scenery image not meant for direct interaction."),
        ("platform",    "Standable surface piece for platformer or jump-puzzle levels."),
        ("ui",          "User-interface graphic: button, panel, frame, HUD element."),
        ("icon",        "Small symbolic graphic representing a stat, item, or action."),
        ("effect",      "Visual effect such as explosion, particle, glow, or smoke."),
        ("projectile",  "Travelling object like bullet, arrow, magic bolt."),
        ("prop",        "Static decorative object placed inside a scene."),
        ("item",        "Pickup or inventory object: potion, coin, key, gem."),
        ("inventory_item", "Specific inventory pickup — crown, sword, potion, gem, scroll, or other carry-and-use object."),
        ("ui_icon",     "Stand-alone UI button or HUD icon graphic — settings cog, heart, coin counter."),
        ("vehicle",     "Mode of transport: car, ship, mount, spaceship."),
        ("machine",     "Mechanical device or robot, often technological."),
        ("building",    "Architectural structure: house, tower, fortress."),
        ("furniture",   "Indoor furnishing: chair, table, bed, shelf."),
        ("plant",       "Vegetation: tree, bush, flower, grass."),
        ("terrain",     "Large-scale ground feature: hill, cliff, beach."),
        ("weapon",      "Tool used to attack or defend, melee or ranged."),
        ("food",        "Edible item or consumable resource."),
        ("portrait",    "Bust or headshot artwork of a character."),
        ("decoration",  "Ornamental detail with no gameplay function."),
        ("other",       "Falls outside the listed categories; see description."),
    ],
    "style": [
        ("pixel_art",     "Low-resolution sprite art with visible square pixels and limited palette."),
        ("vector_flat",   "Crisp flat shapes drawn with vector tools, no gradients."),
        ("hand_drawn",    "Artwork showing visible pencil, ink, or brush strokes."),
        ("painterly",     "Loose painted brushwork with soft edges and color blending."),
        ("sketch",        "Rough line drawing, often monochrome and unfinished."),
        ("anime",         "Japanese animation style with cel shading and large eyes."),
        ("comic",         "Western comic-book ink-and-color style with bold outlines."),
        ("cel_shaded",    "3D rendering with hard shading bands mimicking 2D animation."),
        ("3d_render",     "Image rendered from a 3D model with realistic shading."),
        ("low_poly",      "3D art with deliberately low polygon counts and flat facets."),
        ("voxel",         "3D art built from cubic voxels, similar to Minecraft."),
        ("photo",         "Photographic or photo-realistic imagery."),
        ("retro_8bit",    "Very limited palette evoking 8-bit consoles."),
        ("isometric_2d",  "2D art drawn from a fixed 30-degree isometric angle."),
    ],
    "mood": [
        ("heroic",       "Bold, courageous, larger-than-life energy."),
        ("epic",         "Grand-scale, sweeping, momentous feel."),
        ("triumphant",   "Conveys victory or successful achievement."),
        ("hopeful",      "Optimistic, looking forward to a brighter outcome."),
        ("wholesome",    "Warm and family-friendly, comforting."),
        ("cute",         "Adorable and endearing, often round shapes and pastels."),
        ("playful",      "Light-hearted and fun, inviting interaction."),
        ("comic_relief", "Humorous or absurd, breaking tension."),
        ("romantic",     "Tender, affectionate, love-themed."),
        ("serious",      "Sober, grounded, without humor."),
        ("intense",      "Highly charged emotion or action."),
        ("tense",        "Suspenseful or anxious atmosphere."),
        ("dramatic",     "Theatrical, high-contrast emotional weight."),
        ("chaotic",      "Disorderly or frenetic energy."),
        ("mysterious",   "Hidden, unexplained, intriguing."),
        ("creepy",       "Unsettling, eerie, slightly horror-adjacent."),
        ("dark",         "Bleak, ominous, low-light atmosphere."),
        ("melancholic",  "Sad and reflective, gentle sorrow."),
        ("sad",          "Plainly downcast or sorrowful."),
        ("calm",         "Steady and unhurried, relaxing."),
        ("peaceful",     "Serene and conflict-free."),
        ("nostalgic",    "Evokes memory of past eras or childhood."),
        ("neutral",      "Flat affect — no strong emotional valence."),
        ("minimalist",   "Sparse, restrained, clean — minimal visual or emotional cues."),
    ],
    "palette": [
        ("warm",         "Dominantly reds, oranges, yellows."),
        ("cool",         "Dominantly blues, greens, purples."),
        ("neutral",      "Balanced or grayscale-leaning palette."),
        ("monochrome",   "Single hue plus black/white variations."),
        ("high_contrast", "Strong dark-to-light separation, punchy black/white anchor."),
        ("vibrant",      "Highly saturated, energetic colors."),
        ("saturated",    "Rich color intensity throughout."),
        ("muted",        "Subdued, low-saturation palette."),
        ("desaturated",  "Almost grayscale with slight color tint."),
        ("dark",         "Overall low-luminance palette."),
        ("light",        "Overall high-luminance palette."),
        ("pastel",       "Soft, light, slightly washed-out tones."),
        ("earthy",       "Browns, tans, ochres, forest greens."),
    ],
    "color": [
        ("red_palette",     "Red is the dominant hue."),
        ("blue_palette",    "Blue is the dominant hue."),
        ("green_palette",   "Green is the dominant hue."),
        ("yellow_palette",  "Yellow is the dominant hue."),
        ("purple_palette",  "Purple/violet dominates."),
        ("orange_palette",  "Orange dominates."),
        ("pink_palette",    "Pink or magenta dominates."),
        ("teal_palette",    "Teal or cyan dominates."),
        ("crimson_palette", "Deep dark red dominates."),
        ("gold_palette",    "Metallic gold/yellow dominates."),
        ("silver_palette",  "Metallic silver/gray dominates."),
        ("black_palette",   "Black is dominant."),
        ("white_palette",   "White is dominant."),
        ("gray_palette",    "Neutral grays dominate."),
        ("earth_palette",   "Browns, ochres, and natural tones dominate."),
        ("sepia_palette",   "Warm brown-tinted monochrome."),
    ],
    "view": [
        ("side_view",      "Viewed from the side, classic platformer angle."),
        ("top_down",       "Looking straight down from above."),
        ("isometric",      "Fixed 30-degree axonometric angle."),
        ("front_view",     "Facing the viewer head-on."),
        ("back_view",      "Subject's back faces the viewer."),
        ("three_quarter",  "Slightly angled view between front and side."),
        ("overhead",       "Bird's-eye perspective with slight angle."),
        ("perspective",    "True perspective projection with vanishing points."),
        ("orthographic",   "Parallel projection without perspective foreshortening."),
    ],
    "material": [
        ("wood",    "Wood grain or planks visible."),
        ("metal",   "Reflective or matte metallic surface."),
        ("stone",   "Stone or rock texture."),
        ("cloth",   "Woven fabric, cloth, or tapestry."),
        ("leather", "Tanned hide or leather surface."),
        ("glass",   "Transparent or translucent glass."),
        ("water",   "Liquid water, lake, sea, or splash."),
        ("fire",    "Flame, ember, or burning element."),
        ("ice",     "Frozen surface, snow, or crystal."),
        ("organic", "Living tissue, plant matter, or flesh."),
        ("paper",   "Paper, parchment, or scroll."),
        ("plastic", "Synthetic glossy plastic surface."),
    ],
    "lighting": [
        ("bright",     "Brightly and evenly lit scene."),
        ("dim",        "Subdued or low-intensity lighting."),
        ("neon",       "Glowing neon or fluorescent light sources."),
        ("candlelit",  "Warm flickering candle or torch light."),
        ("sunlit",     "Strong directional sunlight."),
        ("moonlit",    "Cool, soft moonlight."),
        ("shadowy",    "Heavy shadows, high contrast, low-key lighting."),
    ],
    "time_of_day": [
        ("dawn",         "Just before sunrise, soft cool light."),
        ("day",          "Bright midday lighting."),
        ("dusk",         "Twilight after sunset, warm orange sky."),
        ("night",        "After dark, cool tones."),
        ("golden_hour",  "Warm-tinted hour just after sunrise or before sunset."),
    ],
    "weather": [
        ("clear",   "No precipitation, calm sky."),
        ("rainy",   "Active rainfall visible."),
        ("snowy",   "Snow falling or accumulated."),
        ("foggy",   "Heavy fog or mist reducing visibility."),
        ("stormy",  "Storm clouds, lightning, heavy weather."),
        ("sunny",   "Strong sun and clear sky."),
        ("windy",   "Visible wind effects on hair, cloth, foliage."),
    ],
    "theme": [
        ("dungeon",     "Subterranean stone corridors, traps, treasure."),
        ("forest",      "Wooded outdoor environment."),
        ("ocean",       "Open sea or coastal water scene."),
        ("desert",      "Sandy arid landscape."),
        ("mountain",    "Rocky peaks or alpine terrain."),
        ("castle",      "Medieval fortified architecture."),
        ("village",     "Small rural human settlement."),
        ("cave",        "Natural underground cavern."),
        ("space",       "Outer space, stars, planets."),
        ("underwater",  "Below the water surface."),
        ("jungle",      "Dense tropical rainforest."),
        ("swamp",       "Wetland with murky water and twisted plants."),
    ],
    "size_hint": [
        ("tiny",    "Extremely small asset, e.g. 8x8 to 16x16 sprite."),
        ("small",   "Compact asset, e.g. 32x32 sprite."),
        ("medium",  "Standard size, e.g. 64x64 to 128x128."),
        ("large",   "Big asset, e.g. boss sprite or 256+ px."),
        ("huge",    "Full-screen or backdrop-scale image."),
    ],
    "domain": [
        ("fantasy",              "Magic, knights, dragons, classic high-fantasy tropes."),
        ("sci_fi",               "Futuristic technology, space, robotics."),
        ("cyberpunk",            "High tech meets low life, neon megacity dystopia."),
        ("steampunk",            "Victorian-era brass and steam-powered machinery."),
        ("modern",               "Contemporary real-world setting."),
        ("medieval",             "European Middle Ages aesthetics."),
        ("victorian",            "19th-century European elegance."),
        ("western",              "American old-west cowboy setting."),
        ("post_apocalyptic",     "Ruined civilization after a catastrophe."),
        ("mythological",         "Ancient myths and pantheons (Greek, Norse, etc.)."),
        ("prehistoric",          "Stone age, dinosaurs, primal humans."),
        ("futuristic",           "Near-future advanced civilization."),
        ("magical",              "Magic-saturated scene regardless of era."),
        ("military",             "Modern or near-future military equipment."),
        ("urban",                "Cityscape, streets, urban infrastructure."),
        ("rural",                "Countryside, farmland, small towns."),
        ("casual",               "Bright, simple casual-game aesthetic."),
        ("racing",               "Vehicles and racetrack imagery."),
        ("puzzle",               "Abstract block, gem, or board-game pieces."),
        ("horror",               "Frightening, gory, or supernatural-horror imagery."),
        ("japanese_traditional", "Edo-period Japan, kimono, samurai, sumi-e."),
        ("mecha",                "Giant piloted humanoid robots."),
    ],
    "animation": [
        ("idle",    "Resting or breathing loop while not acting."),
        ("walk",    "Steady walking cycle."),
        ("run",     "Faster running cycle."),
        ("jump",    "Take-off and airborne frames."),
        ("attack",  "Strike, swing, or shoot action."),
        ("hurt",    "Take-damage reaction frames."),
        ("death",   "Defeated or dying animation."),
        ("cast",    "Spell-casting or ability activation."),
        ("crouch",  "Lowered defensive stance."),
        ("dodge",   "Quick evasive sidestep or roll."),
        ("block",   "Defensive block or parry."),
        ("climb",   "Climbing ladder or wall."),
        ("swim",    "Swimming locomotion."),
        ("fly",     "Flying or hovering."),
        ("sleep",   "Resting or unconscious."),
        ("other",   "Animation that does not match the listed actions."),
    ],
    # ── 사운드 10축 (CLIP 점수 없음, Gemma 만) ─────────────────────
    "sound_category": [
        ("sfx",          "Discrete sound effect such as hit, jump, or pickup."),
        ("bgm",          "Background music track."),
        ("voice",        "Spoken voice line or narration."),
        ("ui_sound",     "Interface sound: click, hover, confirm."),
        ("ambient",      "Looping environmental ambience or atmosphere bed."),
        ("jingle",       "Short musical motif under ~5s such as victory/level-up cue."),
        ("stinger",      "Brief musical hit used as transition or emphasis."),
        ("foley",        "Realistic everyday sound: footsteps, cloth, object handling."),
        ("narration",    "Story-telling voice over multiple sentences."),
        ("loop",         "Sound explicitly designed to loop seamlessly."),
        ("oneshot",      "Single non-looping playback intended to fire once."),
        ("cinematic",    "Cutscene-grade music or sound design segment."),
    ],
    "sound_mood": [
        ("energetic",   "Upbeat, high-energy."),
        ("calm",        "Relaxing, low-energy."),
        ("eerie",       "Unsettling and atmospheric."),
        ("triumphant",  "Victorious fanfare."),
        ("sad",         "Sorrowful or downcast."),
        ("suspenseful", "Builds tension and unease."),
        ("cheerful",    "Happy and bouncy."),
        ("dark",        "Ominous and brooding."),
        ("mysterious",  "Curious, unresolved."),
        ("intense",     "Driving and powerful."),
        ("peaceful",    "Tranquil and gentle."),
        ("dramatic",    "Sweeping emotional weight."),
        ("heroic",      "Bold, courageous, larger-than-life."),
        ("melancholic", "Reflective, quietly mournful."),
        ("romantic",    "Tender, affectionate."),
        ("comedic",     "Funny, slapstick, lighthearted."),
        ("epic",        "Grand, momentous, sweeping scale."),
        ("hopeful",     "Optimistic and forward-looking."),
        ("ominous",     "Threat-suggesting, foreboding."),
        ("playful",     "Light-hearted, mischievous."),
        ("nostalgic",   "Evokes memory of past eras."),
        ("aggressive",  "Hostile, attacking energy."),
    ],
    "sound_timbre": [
        ("bright",     "Crisp, high-frequency-rich tone."),
        ("dark",       "Low-frequency-rich, warm tone."),
        ("harsh",      "Rough, abrasive, distorted edge."),
        ("soft",       "Gentle, mellow texture."),
        ("metallic",   "Ringing metal quality."),
        ("organic",    "Natural acoustic source feel."),
        ("electronic", "Synthesized or electronic origin."),
        ("acoustic",   "Played on real acoustic instruments."),
        ("distorted",  "Heavily processed, clipped, or fuzzed."),
        ("clean",      "Unprocessed, dry signal."),
        ("warm",       "Rich low-mids, friendly tonal feel."),
        ("sharp",      "Pointed, cutting high frequencies."),
        ("gritty",     "Textured, dirty, lo-fi character."),
        ("hollow",     "Resonant with notch in mids, tube-like."),
        ("percussive", "Transient-dominant, drum-like."),
        ("watery",     "Wet, modulated, chorus/flange-like."),
    ],
    "sound_environment": [
        ("indoor",            "Small reverberant room or interior space."),
        ("outdoor",           "Open air, minimal reverb."),
        ("underwater",        "Muffled, low-pass-filtered underwater feel."),
        ("cave",              "Long deep reverberation."),
        ("hall",              "Large hall reverb, concert-hall scale."),
        ("forest",            "Outdoor woodland ambience with foliage."),
        ("city",              "Urban traffic and crowd noise feel."),
        ("space",             "Vacuum-like sparse, alien feel."),
        ("dungeon",           "Cold stone corridors with dripping echoes."),
        ("ocean",             "Open water, waves, gulls."),
        ("vehicle_interior",  "Inside a moving vehicle, engine bed."),
        ("sewer",             "Damp tunnels with metallic drips."),
        ("sky",               "Open air, wind, altitude."),
        ("tavern",            "Indoor public house, crowd chatter."),
    ],
    "sound_instrument": [
        ("piano",       "Acoustic or electric piano."),
        ("strings",     "Bowed string section: violins, violas, cellos."),
        ("brass",       "Brass section: trumpets, trombones, horns."),
        ("woodwinds",   "Wind instruments: flute, clarinet, oboe."),
        ("percussion",  "Tuned or untuned percussion broadly."),
        ("drums",       "Drum kit or rhythm percussion."),
        ("synth",       "Electronic synthesizer."),
        ("choir",       "Vocal ensemble singing wordless or text."),
        ("guitar",      "Acoustic or electric guitar."),
        ("bass",        "Bass guitar or upright bass."),
        ("organ",       "Pipe organ or electric organ."),
        ("harp",        "Concert harp or small harp."),
        ("bell",        "Tuned bell or chime."),
        ("flute",       "Flute or recorder family solo."),
        ("vocal_solo",  "Single sung voice (wordless or lyrical)."),
        ("orchestra",   "Full symphonic ensemble."),
    ],
    "sound_tempo": [
        ("very_slow",  "Below ~60 BPM, ballad or atmospheric pacing."),
        ("slow",       "Roughly 60-90 BPM."),
        ("medium",     "Roughly 90-120 BPM, walking pace."),
        ("fast",       "Roughly 120-150 BPM, action pace."),
        ("very_fast",  "Above ~150 BPM, frantic pace."),
        ("variable",   "Tempo shifts or has no fixed tempo."),
    ],
    "sound_intensity": [
        ("quiet",         "Whisper-level, easy to overlook."),
        ("soft",          "Low background level."),
        ("moderate",      "Comfortable foreground level."),
        ("loud",          "Attention-grabbing, prominent."),
        ("deafening",     "Overwhelming, full mix dominator."),
        ("swelling",      "Gradually builds in volume."),
        ("sudden_burst",  "Quick spike with sharp attack."),
    ],
    "sound_use": [
        ("action",          "Fits action gameplay segments."),
        ("exploration",     "Fits exploration or traversal."),
        ("combat",          "Fits combat encounters."),
        ("victory",         "Plays on player success."),
        ("defeat",          "Plays on player failure."),
        ("level_complete",  "Marks stage completion."),
        ("game_over",       "Marks game-over state."),
        ("menu",            "Plays in menu/title screens."),
        ("dialogue",        "Plays under or as dialogue line."),
        ("cutscene",        "Plays in cinematic cutscene."),
        ("transition",      "Marks scene/area transition."),
        ("item_pickup",     "Plays when collecting an item."),
        ("achievement",     "Plays on achievement unlock."),
        ("alert",           "Warning or notification cue."),
        ("ambience_loop",   "Steady background loop without melody."),
        ("hit_impact",      "Plays on hit or impact event."),
    ],
    "sound_genre": [
        ("orchestral",       "Symphonic acoustic ensemble style."),
        ("electronic",       "Broad electronic / EDM-adjacent."),
        ("rock",             "Guitar-driven rock idiom."),
        ("jazz",             "Jazz harmony and swing/swing-adjacent rhythm."),
        ("classical",        "European classical period style."),
        ("ambient_music",    "Atmospheric music without strong beat."),
        ("chiptune",         "Retro 8/16-bit console synth music."),
        ("folk",             "Traditional folk instrumentation."),
        ("hip_hop",          "Hip-hop beat and production."),
        ("world",            "Non-Western folk or world-fusion style."),
        ("lofi",             "Lo-fi hip-hop/beats aesthetic."),
        ("cinematic_score",  "Hollywood-style film-score idiom."),
        ("synthwave",        "Retro 80s-inspired synth music."),
        ("metal",            "Heavy metal subgenres."),
    ],
    "sound_voice_type": [
        ("male_adult",     "Adult male voice."),
        ("female_adult",   "Adult female voice."),
        ("male_child",     "Boy or young male voice."),
        ("female_child",   "Girl or young female voice."),
        ("elderly",        "Old-sounding voice regardless of gender."),
        ("narrator",       "Even, story-telling narrator delivery."),
        ("monster_growl",  "Non-human growling or roaring."),
        ("robot",          "Robotic or vocoded voice."),
        ("alien",          "Otherworldly stylized voice."),
        ("whisper",        "Whispered or breathy delivery."),
        ("shouting",       "Yelled or projected delivery."),
        ("singing",        "Sung rather than spoken."),
    ],
}


# ── LabelRegistry ───────────────────────────────────────────────────


# Token tokens we read from the seed map but also accept from add_label —
# the seed entries are pre-validated by hand, but user input goes
# through ``_validate_token`` first.


class LabelRegistry:
    """DB-backed label vocabulary with an in-memory cache.

    Everyone (analyzer, CLIP labeler, future search backend, M3 MCP
    tools) goes through this object to look up labels, so disabling a
    label is immediately reflected in the next analysis without
    requiring a process restart.
    """

    def __init__(self, store: "Store") -> None:
        self.store = store
        # axis → list[str] (enabled-only, sorted) ; ``None`` means cold cache.
        self._cache_enabled: dict[str, list[str]] | None = None

    # -- seeding ------------------------------------------------------

    def bootstrap(
        self, seed: dict[str, list[tuple[str, str]]] | None = None
    ) -> int:
        """Insert seed labels only when the table is empty.  Idempotent."""
        with self.store.write_lock:
            rows = self.store.conn.execute(
                "SELECT COUNT(*) FROM labels"
            ).fetchone()
            if rows and rows[0] > 0:
                return 0
            now = int(time.time())
            seed = seed if seed is not None else SEED_LABELS
            inserted = 0
            self.store.conn.execute("BEGIN")
            try:
                for axis, items in seed.items():
                    for token, desc in items:
                        self.store.conn.execute(
                            "INSERT INTO labels"
                            " (axis, label, description, source, enabled,"
                            "  created_at, updated_at)"
                            " VALUES (?, ?, ?, 'seed', 1, ?, ?)",
                            (axis, token, desc, now, now),
                        )
                        inserted += 1
                self.store.conn.execute("COMMIT")
            except Exception:
                self.store.conn.execute("ROLLBACK")
                raise
            self.invalidate()
            return inserted

    # -- reads --------------------------------------------------------

    def list_axes(self) -> list[str]:
        rows = self.store.conn.execute(
            "SELECT DISTINCT axis FROM labels ORDER BY axis"
        ).fetchall()
        return [r[0] for r in rows]

    def list_labels(
        self,
        axis: str | None = None,
        *,
        enabled_only: bool = True,
        with_description: bool = False,
    ) -> list:
        """Return label tokens for ``axis``.

        * ``with_description=False`` (default) → plain ``list[str]`` of
          enabled labels, sorted by label name.  Hot path: served from
          memory cache.
        * ``with_description=True`` → ``list[LabelRow]`` direct from the
          DB (no cache).  The admin dialog and MCP ``describe_label``
          use this form.
        """
        if with_description or not enabled_only:
            return self.store.list_labels_raw(
                axis=axis, enabled_only=enabled_only
            )

        if self._cache_enabled is None:
            self._refresh_cache()
        assert self._cache_enabled is not None
        if axis is not None:
            return list(self._cache_enabled.get(axis, []))
        merged: list[str] = []
        for axis_name in sorted(self._cache_enabled.keys()):
            merged.extend(self._cache_enabled[axis_name])
        return merged

    def _refresh_cache(self) -> None:
        rows = self.store.list_labels_raw(axis=None, enabled_only=True)
        cache: dict[str, list[str]] = {}
        for r in rows:
            cache.setdefault(r.axis, []).append(r.label)
        # ensure deterministic order
        for axis_name in cache:
            cache[axis_name].sort()
        self._cache_enabled = cache

    # -- writes -------------------------------------------------------

    def add_label(
        self,
        axis: str,
        label: str,
        *,
        source: str = "user",
        description: str | None = None,
    ) -> tuple[int, bool]:
        """Insert or reactivate ``(axis, label)``.

        Returns ``(label_id, was_new)``.  When the pair already exists
        the row is re-enabled (and description updated if given) and
        ``was_new=False``.
        """
        _validate_token(label)
        now = int(time.time())
        with self.store.write_lock:
            cur = self.store.conn.execute(
                "SELECT id, enabled FROM labels WHERE axis = ? AND label = ?",
                (axis, label),
            )
            existing = cur.fetchone()
            if existing is None:
                self.store.conn.execute(
                    "INSERT INTO labels (axis, label, description, source,"
                    " enabled, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (axis, label, description, source, now, now),
                )
                row_id = int(
                    self.store.conn.execute(
                        "SELECT id FROM labels WHERE axis = ? AND label = ?",
                        (axis, label),
                    ).fetchone()[0]
                )
                self.invalidate()
                return row_id, True

            row_id = int(existing[0])
            if description is not None:
                self.store.conn.execute(
                    "UPDATE labels SET enabled = 1, description = ?, updated_at = ?"
                    " WHERE id = ?",
                    (description, now, row_id),
                )
            else:
                self.store.conn.execute(
                    "UPDATE labels SET enabled = 1, updated_at = ? WHERE id = ?",
                    (now, row_id),
                )
            self.invalidate()
            return row_id, False

    def set_enabled(self, axis: str, label: str, enabled: bool) -> None:
        now = int(time.time())
        with self.store.write_lock:
            self.store.conn.execute(
                "UPDATE labels SET enabled = ?, updated_at = ?"
                " WHERE axis = ? AND label = ?",
                (1 if enabled else 0, now, axis, label),
            )
            self.invalidate()

    def set_description(
        self, axis: str, label: str, description: str | None
    ) -> None:
        now = int(time.time())
        with self.store.write_lock:
            self.store.conn.execute(
                "UPDATE labels SET description = ?, updated_at = ?"
                " WHERE axis = ? AND label = ?",
                (description, now, axis, label),
            )
            self.invalidate()

    # -- catalog signature -------------------------------------------

    def label_catalog_signature(self) -> str:
        """16-hex sha256 over the *full* vocabulary state.

        Hashes axis/label/description/enabled across **every** row so
        disabling a label changes the signature too — M3 MCP clients
        use this as a cache key, and a vocabulary that toggles
        availability is observably different from one where the
        label was never present.
        """
        rows = self.store.conn.execute(
            "SELECT axis, label, COALESCE(description, ''), enabled"
            " FROM labels ORDER BY axis, label"
        ).fetchall()
        h = hashlib.sha256()
        for axis, label, desc, enabled in rows:
            h.update(axis.encode("utf-8"))
            h.update(b"\x1f")
            h.update(label.encode("utf-8"))
            h.update(b"\x1f")
            h.update(desc.encode("utf-8"))
            h.update(b"\x1f")
            h.update(b"1" if enabled else b"0")
            h.update(b"\x1e")
        return h.hexdigest()[:16]

    # -- cache invalidation ------------------------------------------

    def invalidate(self) -> None:
        """Drop the in-memory cache; next read repopulates from DB."""
        self._cache_enabled = None
