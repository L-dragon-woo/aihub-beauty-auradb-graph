"""AuraDB graph contracts and Cypher artifact generation."""

from __future__ import annotations

CORE_LABELS = [
    "Dataset",
    "SourceFile",
    "Image",
    "Document",
    "Chunk",
    "QA",
    "Ingredient",
    "SkinConcern",
    "SkinType",
    "SkinCondition",
    "FaceRegion",
    "Effect",
    "Caution",
    "ExternalFactor",
    "Recommendation",
    "Evidence",
]

FULLTEXT_INDEXES = {
    "chunk_text": ("Chunk", ["text"]),
    "qa_text": ("QA", ["question", "answer"]),
    "ingredient_alias": ("Ingredient", ["canonical_name_ko", "canonical_name_en", "aliases"]),
    "concern_alias": ("SkinConcern", ["canonical_name_ko", "aliases"]),
    "caution_alias": ("Caution", ["canonical_name_ko", "aliases"]),
    "recommendation_text": ("Recommendation", ["text"]),
}

READINESS_QUERIES = {
    "future_cag_concern_to_ingredient": """
MATCH (concern:SkinConcern)<-[:TARGETS]-(rec:Recommendation)-[:USES_INGREDIENT]->(ingredient:Ingredient)
OPTIONAL MATCH (ingredient)-[:HAS_EFFECT]->(effect:Effect)
OPTIONAL MATCH (rec)-[:SUPPORTED_BY]->(evidence)
RETURN concern.id, rec.id, ingredient.id, collect(DISTINCT effect.id) AS effects, collect(DISTINCT evidence.id) AS evidence
LIMIT 25;
""".strip(),
    "future_graphrag_chunk_expansion": """
MATCH (chunk:Chunk)-[:MENTIONS]->(entity)
OPTIONAL MATCH (entity)<-[:USES_INGREDIENT|TARGETS|HAS_CAUTION|HAS_EFFECT]-(rec:Recommendation)
RETURN chunk.id, labels(entity) AS entity_labels, entity.id, collect(DISTINCT rec.id) AS recommendations
LIMIT 25;
""".strip(),
}


def constraint_cypher() -> list[str]:
    return [
        f"CREATE CONSTRAINT {label.lower()}_id_unique IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE;"
        for label in CORE_LABELS
    ]


def fulltext_cypher() -> list[str]:
    statements: list[str] = []
    for name, (label, fields) in FULLTEXT_INDEXES.items():
        props = ", ".join(f"n.{field}" for field in fields)
        statements.append(
            f"CREATE FULLTEXT INDEX {name}_fulltext IF NOT EXISTS FOR (n:{label}) ON EACH [{props}];"
        )
    return statements


def vector_cypher(label: str = "Chunk", property_name: str = "embedding", dimensions: int = 1536) -> str:
    return (
        f"CREATE VECTOR INDEX {label.lower()}_{property_name}_vector IF NOT EXISTS "
        f"FOR (n:{label}) ON (n.{property_name}) OPTIONS {{indexConfig: {{"
        f"`vector.dimensions`: {dimensions}, `vector.similarity_function`: 'cosine'}}}};"
    )


def schema_cypher(include_vector: bool = False) -> str:
    statements = constraint_cypher() + fulltext_cypher()
    if include_vector:
        statements.append(vector_cypher())
    return "\n".join(statements) + "\n"
