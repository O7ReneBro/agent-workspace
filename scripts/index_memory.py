"""
index_memory.py — Index memory/notes/ into a local Chroma vector store.

Usage:
    python scripts/index_memory.py          # index all notes
    python scripts/index_memory.py --query "agent memory design"

Requires:
    pip install chromadb sentence-transformers
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

NOTES_DIR = REPO_ROOT / "memory" / "notes"
CHROMA_PATH = str(REPO_ROOT / "memory" / ".chroma")
COLLECTION_NAME = "agent-notes"


def get_collection():
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        print("Error: chromadb not installed. Run: pip install chromadb sentence-transformers")
        sys.exit(1)

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
    )
    return collection


def index_notes() -> int:
    """Index all .md files in memory/notes/ into Chroma. Returns count indexed."""
    collection = get_collection()
    notes = list(NOTES_DIR.glob("*.md"))
    if not notes:
        print("No notes found to index.")
        return 0

    docs, ids, metas = [], [], []
    for note in notes:
        content = note.read_text(encoding="utf-8")
        doc_id = note.stem
        docs.append(content)
        ids.append(doc_id)
        metas.append({"path": str(note.relative_to(REPO_ROOT)), "filename": note.name})

    collection.upsert(documents=docs, ids=ids, metadatas=metas)
    print(f"Indexed {len(docs)} notes into Chroma at {CHROMA_PATH}")
    return len(docs)


def query_notes(query: str, n_results: int = 5) -> list[dict]:
    """Semantic search over indexed notes."""
    collection = get_collection()
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
    )
    output = []
    for i, doc in enumerate(results["documents"][0]):
        output.append(
            {
                "id": results["ids"][0][i],
                "path": results["metadatas"][0][i]["path"],
                "distance": results["distances"][0][i],
                "snippet": doc[:300],
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Index or query memory notes.")
    parser.add_argument("--query", help="Semantic query to run against indexed notes.")
    parser.add_argument("--n", type=int, default=5, help="Number of results to return.")
    args = parser.parse_args()

    if args.query:
        results = query_notes(args.query, n_results=args.n)
        print(f"\nTop {args.n} results for: '{args.query}'\n")
        for r in results:
            print(f"  [{r['distance']:.3f}] {r['path']}")
            print(f"           {r['snippet']}...\n")
    else:
        index_notes()


if __name__ == "__main__":
    main()
