import re
import unicodedata


def canonical_beach_name(name):
    normalized = unicodedata.normalize("NFKD", name or "")
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    simplified = re.sub(r"\b(praia|beach|do|da|de|das|dos)\b", " ", ascii_name, flags=re.IGNORECASE)
    simplified = re.sub(r"[^a-z0-9]+", " ", simplified.casefold()).strip()
    return re.sub(r"\s+", " ", simplified)


SURF_SPOT_METADATA = {}


def register_spot(*names, label, degrees):
    metadata = {
        "preferred_swell_label": label,
        "preferred_swell_degrees": degrees,
    }
    for name in names:
        SURF_SPOT_METADATA[canonical_beach_name(name)] = metadata


# Florianopolis
register_spot("Joaquina", "Joaquina Beach", label="E / SE", degrees=[90, 135])
register_spot("Praia Mole", "Mole", label="E / SE", degrees=[90, 135])
register_spot("Campeche", "Praia do Campeche", label="E / SE", degrees=[90, 135])
register_spot("Galheta", "Praia da Galheta", label="E / SE", degrees=[90, 135])
register_spot("Mocambique", "Moçambique", "Praia do Mocambique", "Praia do Moçambique", label="E / SE", degrees=[90, 135])
register_spot("Santinho", "Praia do Santinho", label="E / NE", degrees=[90, 45])
register_spot("Brava Floripa", "Praia Brava", "Brava", label="E / SE", degrees=[90, 135])
register_spot("Barra da Lagoa", label="E / SE", degrees=[90, 135])
register_spot("Ingleses", "Praia dos Ingleses", label="E / NE", degrees=[90, 45])
register_spot("Armacao", "Armação", "Praia da Armacao", "Praia da Armação", label="E / SE", degrees=[90, 135])
register_spot("Matadeiro", "Praia do Matadeiro", label="E / SE", degrees=[90, 135])

# Garopaba e Imbituba
register_spot("Silveira", "Praia da Silveira", "Praia do Silveira", label="SE / S", degrees=[135, 180])
register_spot("Ferrugem", "Praia da Ferrugem", label="S / SE", degrees=[180, 135])
register_spot("Ouvidor", "Praia do Ouvidor", label="S / SE", degrees=[180, 135])
register_spot("Gamboa", "Praia da Gamboa", label="S / SE", degrees=[180, 135])
register_spot("Siriu", "Praia do Siriu", label="E / SE", degrees=[90, 135])
register_spot("Garopaba Central", "Garopaba", label="E / SE", degrees=[90, 135])
register_spot("Praia da Barra", "Barra", label="E / SE", degrees=[90, 135])
register_spot("Praia da Vigia", "Vigia", label="SE / S", degrees=[135, 180])
register_spot("Praia do Rosa", "Rosa", "Rosa Norte", "Rosa Sul", label="S / SE", degrees=[180, 135])
register_spot("Ibiraquera", "Praia de Ibiraquera", label="S / SE", degrees=[180, 135])
register_spot("Luz", "Praia da Luz", label="S / SE", degrees=[180, 135])
register_spot("Praia da Vila", "Vila", label="E / SE", degrees=[90, 135])
register_spot("Praia do Porto", "Porto", label="E / SE", degrees=[90, 135])
register_spot("Ribanceira", "Praia da Ribanceira", label="S / SE", degrees=[180, 135])
register_spot("Guarda do Embau", "Guarda do Embaú", "Guarda", label="S / SE", degrees=[180, 135])
register_spot("Pinheira", "Praia da Pinheira", label="S / SE", degrees=[180, 135])

# Laguna e Jaguaruna
register_spot("Itapiruba", "Itapiruba Norte", "Itapiruba Sul", label="E / SE", degrees=[90, 135])
register_spot("Mar Grosso", label="E / SE", degrees=[90, 135])
register_spot("Cardoso", "Praia do Cardoso", "Farol de Santa Marta", label="S / SE", degrees=[180, 135])
register_spot("Gi", "Praia do Gi", label="E / SE", degrees=[90, 135])
register_spot("Arroio Corrente", label="E / SE", degrees=[90, 135])
register_spot("Jaguaruna", "Praia do Arroio Corrente", label="E / SE", degrees=[90, 135])
register_spot("Campo Bom", label="E / SE", degrees=[90, 135])
register_spot("Cigana", "Praia da Cigana", label="E / SE", degrees=[90, 135])
register_spot("Mane Lome", "Mane Lome", label="E / SE", degrees=[90, 135])

# Rio Grande do Sul
register_spot("Tramandai", "Tramandai", label="E / SE", degrees=[90, 135])
register_spot("Imbe", "Imbé", label="E / SE", degrees=[90, 135])
register_spot("Atlantida", "Atlântida", label="E / SE", degrees=[90, 135])
register_spot("Capao da Canoa", "Capão da Canoa", label="E / SE", degrees=[90, 135])
register_spot("Cidreira", label="E / SE", degrees=[90, 135])
register_spot("Pinhal", "Balneario Pinhal", "Balneário Pinhal", label="E / SE", degrees=[90, 135])
register_spot("Rainha do Mar", label="E / SE", degrees=[90, 135])
register_spot("Magisterio", "Magistério", label="E / SE", degrees=[90, 135])
register_spot("Quintao", "Quintão", label="E / SE", degrees=[90, 135])
register_spot("Xangri la", "Xangri-lá", "Xangri la", label="E / SE", degrees=[90, 135])
register_spot("Curumim", label="E / SE", degrees=[90, 135])
register_spot("Arroio do Sal", label="E / SE", degrees=[90, 135])
register_spot("Rondinha", label="E / SE", degrees=[90, 135])
register_spot("Cassino", "Praia do Cassino", label="E / SE", degrees=[90, 135])
register_spot("Torres", label="E / SE / S", degrees=[90, 135, 180])
register_spot("Guarita", "Praia da Guarita", label="E / SE / S", degrees=[90, 135, 180])
register_spot("Prainha", "Prainha Torres", label="E / SE / S", degrees=[90, 135, 180])
register_spot("Cal", "Praia da Cal", label="E / SE / S", degrees=[90, 135, 180])


def apply_surf_metadata(beach):
    metadata = SURF_SPOT_METADATA.get(canonical_beach_name(beach.get("name", "")), {})
    if not metadata:
        return beach

    enriched = beach.copy()
    enriched.update(metadata)
    return enriched
