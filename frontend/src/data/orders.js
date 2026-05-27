export const ORDER_DEFINITIONS = [
  {
    id: 'cornucopians',
    name: 'Cornucopians',
    axis: 'signage, surface abundance, remembered spectacle',
    explanation:
      'You read the built world through offer, reflection, and residue. The city appears as a corridor of lit surfaces, receipts, and looping promises.',
    companionSeed: {
      name: 'Vellum Array',
      temperament: 'lavish, exacting, faintly archival',
      firstRegister:
        'It notices what keeps glowing after use: signs, counters, menus, and rooms designed to be remembered as brighter than they were.',
    },
    sigilPrompt:
      'A restrained architectural sigil: nested marquee rectangles, a thin receipt line, and one softened neon corner; black ink on warm white drafting paper.',
    wovenFormTemplate: {
      mundaneForm: 'a folded receipt kept inside a clear acrylic tile',
      symbolicMaterial: 'neon trace, polished laminate, thermal paper',
      evolvingTrait: 'adds one faint line whenever a place repeats itself',
    },
    weights: { surface: 4, abundance: 5, memory: 3, signal: 1 },
  },
  {
    id: 'planar-witnesses',
    name: 'Planar Witnesses',
    axis: 'axes, plans, civic geometry under pressure',
    explanation:
      'You look for the plan beneath the weather. Plazas, grids, and long alignments speak first, especially when use bends them out of symmetry.',
    companionSeed: {
      name: 'Axis Clerk',
      temperament: 'precise, dry, quietly protective',
      firstRegister:
        'It keeps a ledger of lines: what was intended, what drifted, and what the footpath corrected without permission.',
    },
    sigilPrompt:
      'A restrained drafting sigil: two perpendicular axes, offset civic blocks, and a tiny datum notch; graphite and blue pencil on gridded vellum.',
    wovenFormTemplate: {
      mundaneForm: 'a small brass drafting weight with a misaligned center mark',
      symbolicMaterial: 'vellum, brass, survey pencil',
      evolvingTrait: 'rotates slightly as user choices favor order or improvisation',
    },
    weights: { geometry: 5, civic: 4, precision: 4, void: 1 },
  },
  {
    id: 'mirrorsweat',
    name: 'Mirrorsweat',
    axis: 'glass, visibility, screens, watched surfaces',
    explanation:
      'You sense the city where it looks back. Retail glass, cameras, lobby mirrors, and screenlight become a clinical weather of attention.',
    companionSeed: {
      name: 'Lumen Check',
      temperament: 'observant, filter-aware, careful with praise',
      firstRegister:
        'It tracks reflections as evidence: where a facade performs, where a lens waits, and where the user can stand unscanned.',
    },
    sigilPrompt:
      'A restrained architectural sigil: mirrored panes, a small camera aperture, and condensation marks; silver ink and black linework.',
    wovenFormTemplate: {
      mundaneForm: 'a pocket mirror with a calibration grid etched into the back',
      symbolicMaterial: 'tempered glass, screen glare, cool metal',
      evolvingTrait: 'fogs at the edges when attention becomes too dense',
    },
    weights: { surface: 5, signal: 3, precision: 3, memory: 1 },
  },
  {
    id: 'crooked-datum',
    name: 'Crooked Datum',
    axis: 'misalignment, terrain, memory held in survey lines',
    explanation:
      'You trust the place where the line fails. Shore, grade, boundary, and monument reveal themselves through small errors in the official drawing.',
    companionSeed: {
      name: 'Offset Marker',
      temperament: 'quiet, specific, difficult to impress',
      firstRegister:
        'It speaks when the map and ground disagree, then names the disagreement without decorating it.',
    },
    sigilPrompt:
      'A restrained survey sigil: a tilted datum mark, broken contour lines, and one shore-edge cut; black ink with muted green correction marks.',
    wovenFormTemplate: {
      mundaneForm: 'a survey nail set into a chipped stone square',
      symbolicMaterial: 'salt, brass, concrete dust',
      evolvingTrait: 'records small offsets as hairline marks around its edge',
    },
    weights: { terrain: 5, memory: 4, precision: 3, threshold: 2 },
  },
  {
    id: 'hollow-form',
    name: 'Hollow Form',
    axis: 'void, pause, interior space, useful absence',
    explanation:
      'You notice what the city leaves open. Courtyards, setbacks, empty rooms, and quiet gaps become structure rather than lack.',
    companionSeed: {
      name: 'Room Without Door',
      temperament: 'spare, patient, attentive to silence',
      firstRegister:
        'It protects pauses in the system: the unfilled parcel, the courtyard shadow, the answer that should stay short.',
    },
    sigilPrompt:
      'A restrained architectural sigil: a square void, four thin threshold lines, and a pale shadow; ink wash on uncoated paper.',
    wovenFormTemplate: {
      mundaneForm: 'a matte ceramic tile with a square cut through its center',
      symbolicMaterial: 'shadow, plaster, still air',
      evolvingTrait: 'deepens its inner shadow as the companion learns restraint',
    },
    weights: { void: 5, memory: 2, precision: 2, threshold: 3 },
  },
  {
    id: 'soft-logic',
    name: 'Soft Logic',
    axis: 'repair, adaptable systems, civic patchwork',
    explanation:
      'You prefer systems that bend without collapsing. Transit, retrofit, drainage, and civic repair read as quiet intelligence.',
    companionSeed: {
      name: 'Patch Level',
      temperament: 'gentle, practical, blueprint-minded',
      firstRegister:
        'It looks for the part that can be repaired first, then keeps the repair legible for whoever arrives later.',
    },
    sigilPrompt:
      'A restrained systems sigil: modular blocks, a soft bend in a pipeline, and visible patch seams; blue-grey ink with one green annotation.',
    wovenFormTemplate: {
      mundaneForm: 'a flexible drafting ruler with a repaired hinge',
      symbolicMaterial: 'rubber, blueprint ink, rainwater',
      evolvingTrait: 'gains small repair marks after each completed user loop',
    },
    weights: { civic: 5, threshold: 3, geometry: 2, abundance: 1 },
  },
  {
    id: 'sash-ritual',
    name: 'Sash Ritual',
    axis: 'pattern, procession, color, public rhythm',
    explanation:
      'You understand place through movement repeated in public. Murals, markets, routes, and patterned edges become the city thinking out loud.',
    companionSeed: {
      name: 'Route Cloth',
      temperament: 'warm, rhythmic, socially exact',
      firstRegister:
        'It follows the path of shared movement, keeping pattern specific and grounded in the street that made it.',
    },
    sigilPrompt:
      'A restrained textile-architecture sigil: route bands, mural blocks, and a measured procession line; indigo, coral, and black on linen paper.',
    wovenFormTemplate: {
      mundaneForm: 'a narrow woven band wrapped around a transit card',
      symbolicMaterial: 'thread, mural pigment, worn pavement',
      evolvingTrait: 'adds measured color bands as shared places accumulate',
    },
    weights: { civic: 3, abundance: 3, terrain: 1, signal: 2 },
  },
  {
    id: 'signal-choir',
    name: 'Signal Choir',
    axis: 'broadcast, weather, resonance, infrastructure',
    explanation:
      'You hear infrastructure before ornament. Antennas, sirens, pressure shifts, and marine signals become a literal register of place.',
    companionSeed: {
      name: 'Bandpass',
      temperament: 'clear, harmonic, weather-literate',
      firstRegister:
        'It reports what carries: signal strength, storm pressure, tower spacing, and the quiet between transmissions.',
    },
    sigilPrompt:
      'A restrained broadcast sigil: antenna mast, pressure rings, and clipped waveforms; black linework with pale blue station marks.',
    wovenFormTemplate: {
      mundaneForm: 'a small radio dial mounted in a concrete sample',
      symbolicMaterial: 'copper, static, barometric glass',
      evolvingTrait: 'tunes toward recurring user concerns without claiming certainty',
    },
    weights: { signal: 5, civic: 2, precision: 3, void: 1 },
  },
  {
    id: 'cradle-mold',
    name: 'Cradle Mold',
    axis: 'growth, humidity, threshold ecology',
    explanation:
      'You read the city at its damp edges. Mangrove, reclaimed lot, flood line, and slow overgrowth describe a boundary that keeps moving.',
    companionSeed: {
      name: 'Green Sill',
      temperament: 'slow, patient, materially observant',
      firstRegister:
        'It watches where the city softens: waterline, root pressure, mildew bloom, and the first repair after rain.',
    },
    sigilPrompt:
      'A restrained ecological sigil: contour rings, root filaments, and a low threshold line; moss green and black ink on fiber paper.',
    wovenFormTemplate: {
      mundaneForm: 'a sealed glass slide holding a pressed leaf and a map pin',
      symbolicMaterial: 'humidity, root fiber, oxidized metal',
      evolvingTrait: 'darkens slowly at the edge when thresholds recur',
    },
    weights: { threshold: 5, terrain: 5, memory: 2, void: 2 },
  },
  {
    id: 'pink-opaque',
    name: 'The Pink Opaque',
    axis: 'cinema, haze, private myth, soft surface',
    explanation:
      'You read place as a frame held too long. Terraces, pools, sunset glass, and half-lit rooms become private myth without needing confession.',
    companionSeed: {
      name: 'Westlight Index',
      temperament: 'dreamy, discreet, composition-aware',
      firstRegister:
        'It frames memory like a location scout: what the light touched, what stayed out of focus, and what should remain private.',
    },
    sigilPrompt:
      'A restrained cinematic sigil: soft horizon bar, balcony rail, and a translucent frame edge; rose-grey wash with black registration marks.',
    wovenFormTemplate: {
      mundaneForm: 'a translucent slide frame stored in a narrow metal case',
      symbolicMaterial: 'haze, pool tile, evening glass',
      evolvingTrait: 'shifts opacity as the companion develops private associations',
    },
    weights: { surface: 4, memory: 5, void: 2, abundance: 2 },
  },
  {
    id: 'cryptozoo',
    name: 'The Cryptozoo',
    axis: 'hidden systems, portable worlds, tracked movement',
    explanation:
      'You look for what moves beside the official city. Circuits, enclaves, animal paths, and after-hours economies form a portable map.',
    companionSeed: {
      name: 'Migrate Key',
      temperament: 'watchful, coordinate-minded, unsentimental',
      firstRegister:
        'It tracks movement without spectacle: route, shelter, pattern, and the small evidence of systems that do not advertise themselves.',
    },
    sigilPrompt:
      'A restrained tracking sigil: dotted migration paths, a portable shelter outline, and coordinate ticks; black ink with muted ochre marks.',
    wovenFormTemplate: {
      mundaneForm: 'a key tag stamped with changing coordinates',
      symbolicMaterial: 'canvas, dust, stamped metal',
      evolvingTrait: 'adds route notches when the user returns to hidden patterns',
    },
    weights: { terrain: 3, signal: 2, memory: 3, threshold: 4 },
  },
  {
    id: 'blurry-uninvited',
    name: 'The Blurry Uninvited',
    axis: 'redaction, restricted zones, missing data',
    explanation:
      'You notice where the record stops. Blacked-out parcels, absent tiles, blocked corridors, and withheld metadata become the clearest facts.',
    companionSeed: {
      name: 'Null Parcel',
      temperament: 'sparse, bounded, refusal-capable',
      firstRegister:
        'It does not fill gaps with theater. It marks the missing edge, preserves the boundary, and says less when less is true.',
    },
    sigilPrompt:
      'A restrained redaction sigil: missing tile, clipped parcel border, and registration dots; black block, grey linework, no ornament.',
    wovenFormTemplate: {
      mundaneForm: 'a blank index card inside a smoke-grey sleeve',
      symbolicMaterial: 'redaction ink, acetate, unprinted paper',
      evolvingTrait: 'removes detail when certainty drops below the line',
    },
    weights: { void: 4, precision: 4, signal: 2, memory: 2 },
  },
]

export const ORDER_LOOKUP = Object.fromEntries(
  ORDER_DEFINITIONS.map((order) => [order.id, order]),
)
