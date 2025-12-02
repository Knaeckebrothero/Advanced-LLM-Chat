// Neo4j Seed Data for Fessi Waste Disposal Knowledge Graph
// Run this script to populate the Neo4j database with sample data for Frankfurt am Main

// === WASTE CATEGORIES ===
CREATE (recycling:WasteCategory {
  id: 'cat-recycling',
  name: 'Recyclables',
  name_de: 'Wertstoffe',
  description: 'Materials that can be recycled into new products'
})

CREATE (organic:WasteCategory {
  id: 'cat-organic',
  name: 'Organic Waste',
  name_de: 'Bioabfall',
  description: 'Biodegradable waste from kitchen and garden'
})

CREATE (hazardous:WasteCategory {
  id: 'cat-hazardous',
  name: 'Hazardous Waste',
  name_de: 'Sondermüll',
  description: 'Waste requiring special handling due to toxic or dangerous properties'
})

CREATE (ewaste:WasteCategory {
  id: 'cat-ewaste',
  name: 'Electronic Waste',
  name_de: 'Elektroschrott',
  description: 'Discarded electrical and electronic devices'
})

CREATE (bulky:WasteCategory {
  id: 'cat-bulky',
  name: 'Bulky Waste',
  name_de: 'Sperrmüll',
  description: 'Large items that do not fit in regular bins'
})

CREATE (residual:WasteCategory {
  id: 'cat-residual',
  name: 'Residual Waste',
  name_de: 'Restmüll',
  description: 'Non-recyclable waste that goes to incineration'
})

// === WASTE ITEMS ===
CREATE (plastic:WasteItem {
  id: 'item-plastic-packaging',
  name: 'Plastic Packaging',
  name_de: 'Plastikverpackungen',
  examples: ['Yogurt cups', 'Shampoo bottles', 'Plastic bags', 'Styrofoam']
})

CREATE (glass:WasteItem {
  id: 'item-glass',
  name: 'Glass',
  name_de: 'Glas',
  examples: ['Wine bottles', 'Jam jars', 'Sauce bottles']
})

CREATE (paper:WasteItem {
  id: 'item-paper',
  name: 'Paper and Cardboard',
  name_de: 'Papier und Pappe',
  examples: ['Newspapers', 'Cardboard boxes', 'Magazines', 'Paper bags']
})

CREATE (batteries:WasteItem {
  id: 'item-batteries',
  name: 'Batteries',
  name_de: 'Batterien',
  examples: ['AA batteries', 'Rechargeable batteries', 'Button cells']
})

CREATE (electronics:WasteItem {
  id: 'item-electronics',
  name: 'Electronics',
  name_de: 'Elektrogeräte',
  examples: ['Smartphones', 'Laptops', 'Toasters', 'Hair dryers']
})

CREATE (tv:WasteItem {
  id: 'item-tv-monitor',
  name: 'TVs and Monitors',
  name_de: 'Fernseher und Monitore',
  examples: ['LED TVs', 'Computer monitors', 'Old CRT TVs']
})

CREATE (furniture:WasteItem {
  id: 'item-furniture',
  name: 'Furniture',
  name_de: 'Möbel',
  examples: ['Sofas', 'Tables', 'Chairs', 'Mattresses']
})

CREATE (food:WasteItem {
  id: 'item-food-waste',
  name: 'Food Waste',
  name_de: 'Essensreste',
  examples: ['Vegetable peels', 'Coffee grounds', 'Eggshells', 'Leftovers']
})

CREATE (garden:WasteItem {
  id: 'item-garden-waste',
  name: 'Garden Waste',
  name_de: 'Gartenabfall',
  examples: ['Leaves', 'Grass clippings', 'Branches', 'Flowers']
})

CREATE (paint:WasteItem {
  id: 'item-paint',
  name: 'Paint and Solvents',
  name_de: 'Farben und Lösungsmittel',
  examples: ['Wall paint', 'Varnish', 'Paint thinner', 'Turpentine']
})

CREATE (medicine:WasteItem {
  id: 'item-medicine',
  name: 'Medicines',
  name_de: 'Medikamente',
  examples: ['Expired pills', 'Ointments', 'Syrups', 'Insulin pens']
})

CREATE (textiles:WasteItem {
  id: 'item-textiles',
  name: 'Textiles',
  name_de: 'Textilien',
  examples: ['Old clothes', 'Shoes', 'Bedding', 'Curtains']
})

// === DISPOSAL METHODS ===
CREATE (yellowBag:DisposalMethod {
  id: 'method-yellow-bag',
  name: 'Yellow Bag/Bin',
  name_de: 'Gelber Sack/Gelbe Tonne',
  type: 'bin',
  color: 'yellow',
  frequency: 'Every 2 weeks',
  instructions: 'Empty and rinse containers. No food residue.'
})

CREATE (glassCont:DisposalMethod {
  id: 'method-glass-container',
  name: 'Glass Container',
  name_de: 'Glascontainer',
  type: 'container',
  color: 'green/white/brown',
  frequency: 'Available 24/7',
  instructions: 'Sort by color: green, brown, white. Remove lids. No ceramics or mirrors.'
})

CREATE (paperBin:DisposalMethod {
  id: 'method-paper-bin',
  name: 'Paper Bin',
  name_de: 'Papiertonne',
  type: 'bin',
  color: 'blue',
  frequency: 'Every 4 weeks',
  instructions: 'Flatten cardboard boxes. No coated or waxed paper.'
})

CREATE (bioBin:DisposalMethod {
  id: 'method-bio-bin',
  name: 'Organic Waste Bin',
  name_de: 'Biotonne',
  type: 'bin',
  color: 'brown',
  frequency: 'Weekly',
  instructions: 'Use paper bags or newspaper. No plastic, even biodegradable.'
})

CREATE (residualBin:DisposalMethod {
  id: 'method-residual-bin',
  name: 'Residual Waste Bin',
  name_de: 'Restmülltonne',
  type: 'bin',
  color: 'black/gray',
  frequency: 'Every 2 weeks',
  instructions: 'For non-recyclable waste only.'
})

CREATE (wertstoffhof:DisposalMethod {
  id: 'method-wertstoffhof',
  name: 'Recycling Center',
  name_de: 'Wertstoffhof',
  type: 'drop-off',
  color: 'n/a',
  frequency: 'Mon-Sat, check hours',
  instructions: 'Bring ID. Some items free, others may have fees.'
})

CREATE (bulkyPickup:DisposalMethod {
  id: 'method-bulky-pickup',
  name: 'Bulky Waste Pickup',
  name_de: 'Sperrmüllabholung',
  type: 'pickup',
  color: 'n/a',
  frequency: 'On request (online/phone)',
  instructions: 'Schedule 2 weeks in advance. Place at curb on collection day.'
})

CREATE (hazardousMobile:DisposalMethod {
  id: 'method-hazardous-mobile',
  name: 'Mobile Hazardous Waste Collection',
  name_de: 'Schadstoffmobil',
  type: 'pickup',
  color: 'n/a',
  frequency: 'Monthly at various locations',
  instructions: 'Check schedule for your district. Max 20kg per visit.'
})

CREATE (textileCont:DisposalMethod {
  id: 'method-textile-container',
  name: 'Textile Container',
  name_de: 'Altkleidercontainer',
  type: 'container',
  color: 'various',
  frequency: 'Available 24/7',
  instructions: 'Clean and dry items only. Pack in bags.'
})

CREATE (batteryBox:DisposalMethod {
  id: 'method-battery-collection',
  name: 'Battery Collection Box',
  name_de: 'Batterie-Sammelbox',
  type: 'drop-off',
  color: 'green',
  frequency: 'Available at supermarkets',
  instructions: 'Tape terminals of lithium batteries.'
})

CREATE (pharmacy:DisposalMethod {
  id: 'method-pharmacy',
  name: 'Pharmacy Return',
  name_de: 'Apotheke',
  type: 'drop-off',
  color: 'n/a',
  frequency: 'During opening hours',
  instructions: 'Most pharmacies accept old medicines voluntarily.'
})

// === LOCATIONS (Frankfurt am Main) ===
CREATE (wsNord:Location {
  id: 'loc-wertstoffhof-nord',
  name: 'Wertstoffhof Frankfurt-Nord',
  address: 'Homburger Landstraße 300',
  city: 'Frankfurt am Main',
  postal_code: '60435',
  lat: 50.1553,
  lng: 8.6842,
  hours: 'Mon-Fri 8:00-17:00, Sat 8:00-14:00',
  phone: '+49 69 212-33333'
})

CREATE (wsSued:Location {
  id: 'loc-wertstoffhof-sued',
  name: 'Wertstoffhof Frankfurt-Süd',
  address: 'Hahnstraße 40',
  city: 'Frankfurt am Main',
  postal_code: '60528',
  lat: 50.0756,
  lng: 8.6234,
  hours: 'Mon-Fri 8:00-17:00, Sat 8:00-14:00',
  phone: '+49 69 212-33333'
})

CREATE (wsOst:Location {
  id: 'loc-wertstoffhof-ost',
  name: 'Wertstoffhof Frankfurt-Ost',
  address: 'Heerstraße 109',
  city: 'Frankfurt am Main',
  postal_code: '60488',
  lat: 50.1234,
  lng: 8.7456,
  hours: 'Mon-Fri 8:00-17:00, Sat 8:00-14:00',
  phone: '+49 69 212-33333'
})

// === FAQs ===
CREATE (faq1:FAQ {
  id: 'faq-yellow-bag',
  question: 'What goes in the yellow bag?',
  question_de: 'Was gehört in den Gelben Sack?',
  answer: 'Plastic packaging, metal cans, composite cartons (Tetra Pak), and aluminum. Must be empty and rinsed.',
  answer_de: 'Plastikverpackungen, Metalldosen, Verbundkartons (Tetra Pak) und Aluminium. Muss leer und ausgespült sein.'
})

CREATE (faq2:FAQ {
  id: 'faq-bulky-waste',
  question: 'How do I dispose of bulky waste?',
  question_de: 'Wie entsorge ich Sperrmüll?',
  answer: 'Schedule a pickup online at fes-frankfurt.de or call 069 212-33333. Alternatively, bring items to a Wertstoffhof.',
  answer_de: 'Termin online auf fes-frankfurt.de oder telefonisch unter 069 212-33333 vereinbaren. Alternativ zum Wertstoffhof bringen.'
})

CREATE (faq3:FAQ {
  id: 'faq-electronics',
  question: 'Where can I dispose of old electronics?',
  question_de: 'Wo kann ich alte Elektrogeräte entsorgen?',
  answer: 'At any Wertstoffhof for free, or at electronics retailers (for devices up to 25cm). Large retailers must accept old devices when buying new ones.',
  answer_de: 'Kostenlos am Wertstoffhof oder bei Elektrohändlern (für Geräte bis 25cm). Große Händler müssen Altgeräte beim Neukauf annehmen.'
});

// === RELATIONSHIPS ===

// Waste items to categories
MATCH (plastic:WasteItem {id: 'item-plastic-packaging'}), (recycling:WasteCategory {id: 'cat-recycling'})
CREATE (plastic)-[:BELONGS_TO]->(recycling);

MATCH (glass:WasteItem {id: 'item-glass'}), (recycling:WasteCategory {id: 'cat-recycling'})
CREATE (glass)-[:BELONGS_TO]->(recycling);

MATCH (paper:WasteItem {id: 'item-paper'}), (recycling:WasteCategory {id: 'cat-recycling'})
CREATE (paper)-[:BELONGS_TO]->(recycling);

MATCH (batteries:WasteItem {id: 'item-batteries'}), (hazardous:WasteCategory {id: 'cat-hazardous'})
CREATE (batteries)-[:BELONGS_TO]->(hazardous);

MATCH (electronics:WasteItem {id: 'item-electronics'}), (ewaste:WasteCategory {id: 'cat-ewaste'})
CREATE (electronics)-[:BELONGS_TO]->(ewaste);

MATCH (tv:WasteItem {id: 'item-tv-monitor'}), (ewaste:WasteCategory {id: 'cat-ewaste'})
CREATE (tv)-[:BELONGS_TO]->(ewaste);

MATCH (furniture:WasteItem {id: 'item-furniture'}), (bulky:WasteCategory {id: 'cat-bulky'})
CREATE (furniture)-[:BELONGS_TO]->(bulky);

MATCH (food:WasteItem {id: 'item-food-waste'}), (organic:WasteCategory {id: 'cat-organic'})
CREATE (food)-[:BELONGS_TO]->(organic);

MATCH (garden:WasteItem {id: 'item-garden-waste'}), (organic:WasteCategory {id: 'cat-organic'})
CREATE (garden)-[:BELONGS_TO]->(organic);

MATCH (paint:WasteItem {id: 'item-paint'}), (hazardous:WasteCategory {id: 'cat-hazardous'})
CREATE (paint)-[:BELONGS_TO]->(hazardous);

MATCH (medicine:WasteItem {id: 'item-medicine'}), (hazardous:WasteCategory {id: 'cat-hazardous'})
CREATE (medicine)-[:BELONGS_TO]->(hazardous);

MATCH (textiles:WasteItem {id: 'item-textiles'}), (recycling:WasteCategory {id: 'cat-recycling'})
CREATE (textiles)-[:BELONGS_TO]->(recycling);

// Waste items to disposal methods
MATCH (plastic:WasteItem {id: 'item-plastic-packaging'}), (yellow:DisposalMethod {id: 'method-yellow-bag'})
CREATE (plastic)-[:DISPOSED_VIA {priority: 1}]->(yellow);

MATCH (glass:WasteItem {id: 'item-glass'}), (glassCont:DisposalMethod {id: 'method-glass-container'})
CREATE (glass)-[:DISPOSED_VIA {priority: 1}]->(glassCont);

MATCH (paper:WasteItem {id: 'item-paper'}), (paperBin:DisposalMethod {id: 'method-paper-bin'})
CREATE (paper)-[:DISPOSED_VIA {priority: 1}]->(paperBin);

MATCH (batteries:WasteItem {id: 'item-batteries'}), (batteryBox:DisposalMethod {id: 'method-battery-collection'})
CREATE (batteries)-[:DISPOSED_VIA {priority: 1}]->(batteryBox);

MATCH (batteries:WasteItem {id: 'item-batteries'}), (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'})
CREATE (batteries)-[:DISPOSED_VIA {priority: 2}]->(wertstoffhof);

MATCH (electronics:WasteItem {id: 'item-electronics'}), (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'})
CREATE (electronics)-[:DISPOSED_VIA {priority: 1}]->(wertstoffhof);

MATCH (tv:WasteItem {id: 'item-tv-monitor'}), (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'})
CREATE (tv)-[:DISPOSED_VIA {priority: 1}]->(wertstoffhof);

MATCH (furniture:WasteItem {id: 'item-furniture'}), (bulkyPickup:DisposalMethod {id: 'method-bulky-pickup'})
CREATE (furniture)-[:DISPOSED_VIA {priority: 1}]->(bulkyPickup);

MATCH (furniture:WasteItem {id: 'item-furniture'}), (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'})
CREATE (furniture)-[:DISPOSED_VIA {priority: 2}]->(wertstoffhof);

MATCH (food:WasteItem {id: 'item-food-waste'}), (bioBin:DisposalMethod {id: 'method-bio-bin'})
CREATE (food)-[:DISPOSED_VIA {priority: 1}]->(bioBin);

MATCH (garden:WasteItem {id: 'item-garden-waste'}), (bioBin:DisposalMethod {id: 'method-bio-bin'})
CREATE (garden)-[:DISPOSED_VIA {priority: 1}]->(bioBin);

MATCH (garden:WasteItem {id: 'item-garden-waste'}), (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'})
CREATE (garden)-[:DISPOSED_VIA {priority: 2, notes: 'For large quantities'}]->(wertstoffhof);

MATCH (paint:WasteItem {id: 'item-paint'}), (hazardousMobile:DisposalMethod {id: 'method-hazardous-mobile'})
CREATE (paint)-[:DISPOSED_VIA {priority: 1}]->(hazardousMobile);

MATCH (paint:WasteItem {id: 'item-paint'}), (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'})
CREATE (paint)-[:DISPOSED_VIA {priority: 2}]->(wertstoffhof);

MATCH (medicine:WasteItem {id: 'item-medicine'}), (pharmacy:DisposalMethod {id: 'method-pharmacy'})
CREATE (medicine)-[:DISPOSED_VIA {priority: 1}]->(pharmacy);

MATCH (medicine:WasteItem {id: 'item-medicine'}), (hazardousMobile:DisposalMethod {id: 'method-hazardous-mobile'})
CREATE (medicine)-[:DISPOSED_VIA {priority: 2}]->(hazardousMobile);

MATCH (textiles:WasteItem {id: 'item-textiles'}), (textileCont:DisposalMethod {id: 'method-textile-container'})
CREATE (textiles)-[:DISPOSED_VIA {priority: 1}]->(textileCont);

// Disposal methods to locations
MATCH (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'}), (wsNord:Location {id: 'loc-wertstoffhof-nord'})
CREATE (wertstoffhof)-[:AVAILABLE_AT]->(wsNord);

MATCH (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'}), (wsSued:Location {id: 'loc-wertstoffhof-sued'})
CREATE (wertstoffhof)-[:AVAILABLE_AT]->(wsSued);

MATCH (wertstoffhof:DisposalMethod {id: 'method-wertstoffhof'}), (wsOst:Location {id: 'loc-wertstoffhof-ost'})
CREATE (wertstoffhof)-[:AVAILABLE_AT]->(wsOst);

MATCH (hazardousMobile:DisposalMethod {id: 'method-hazardous-mobile'}), (wsNord:Location {id: 'loc-wertstoffhof-nord'})
CREATE (hazardousMobile)-[:AVAILABLE_AT]->(wsNord);

// FAQs
MATCH (plastic:WasteItem {id: 'item-plastic-packaging'}), (faq1:FAQ {id: 'faq-yellow-bag'})
CREATE (plastic)-[:HAS_FAQ]->(faq1);

MATCH (furniture:WasteItem {id: 'item-furniture'}), (faq2:FAQ {id: 'faq-bulky-waste'})
CREATE (furniture)-[:HAS_FAQ]->(faq2);

MATCH (electronics:WasteItem {id: 'item-electronics'}), (faq3:FAQ {id: 'faq-electronics'})
CREATE (electronics)-[:HAS_FAQ]->(faq3);

MATCH (tv:WasteItem {id: 'item-tv-monitor'}), (faq3:FAQ {id: 'faq-electronics'})
CREATE (tv)-[:HAS_FAQ]->(faq3);

MATCH (ewaste:WasteCategory {id: 'cat-ewaste'}), (faq3:FAQ {id: 'faq-electronics'})
CREATE (ewaste)-[:HAS_FAQ]->(faq3);
