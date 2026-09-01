import pickle
from typing import List, Dict, Union, Any
from rank_bm25 import BM25Okapi
from .tokenizer import tokenize_zh

class BM25Encoder:
    """
    BM25 Encoder for sparse vector generation compatible with Qdrant.
    Converts text documents and queries into sparse vectors (indices and values)
    by computing BM25 term weights.
    """
    def __init__(self):
        self.bm25: Any = None
        self.vocab: Dict[str, int] = {}
        
    def fit(self, corpus: List[str]) -> None:
        """
        Fit the BM25 model on the given corpus.
        
        Args:
            corpus: List of documents to compute IDF and average document length.
        """
        tokenized_corpus = [tokenize_zh(doc) for doc in corpus]
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        # Build vocabulary mapping (term -> index)
        # BM25Okapi records unique terms in its `idf` dictionary.
        self.vocab = {term: idx for idx, term in enumerate(self.bm25.idf.keys())}
        
    def encode_document(self, text: str) -> Dict[str, List[Union[int, float]]]:
        """
        Encode a document into a sparse vector representation using BM25 scoring.
        
        Args:
            text: Document text to encode.
            
        Returns:
            Dictionary with 'indices' (list of int) and 'values' (list of float).
        """
        if self.bm25 is None:
            raise ValueError("Model is not fitted. Call fit() with a corpus first.")
            
        tokens = tokenize_zh(text)
        if not tokens:
            return {"indices": [], "values": []}
            
        term_counts: Dict[str, int] = {}
        for t in tokens:
            term_counts[t] = term_counts.get(t, 0) + 1
            
        doc_len = len(tokens)
        indices = []
        values = []
        
        for term, tf in term_counts.items():
            if term in self.vocab:
                idx = self.vocab[term]
                idf = self.bm25.idf[term]
                
                # BM25 Document Term Weight Formula:
                # IDF * [ TF * (k1 + 1) ] / [ TF + k1 * (1 - b + b * (|D| / avgdl)) ]
                numerator = idf * tf * (self.bm25.k1 + 1)
                denominator = tf + self.bm25.k1 * (1 - self.bm25.b + self.bm25.b * (doc_len / self.bm25.avgdl))
                weight = numerator / denominator
                
                if weight > 0:
                    indices.append(idx)
                    values.append(float(weight))
                    
        return {"indices": indices, "values": values}

    def encode_query(self, text: str) -> Dict[str, List[Union[int, float]]]:
        """
        Encode a query into a sparse vector representation.
        
        Args:
            text: Query text to encode.
            
        Returns:
            Dictionary with 'indices' (list of int) and 'values' (list of float).
        """
        if self.bm25 is None:
            raise ValueError("Model is not fitted. Call fit() with a corpus first.")
            
        tokens = tokenize_zh(text)
        if not tokens:
            return {"indices": [], "values": []}
            
        term_counts: Dict[str, int] = {}
        for t in tokens:
            term_counts[t] = term_counts.get(t, 0) + 1
            
        indices = []
        values = []
        
        for term, count in term_counts.items():
            if term in self.vocab:
                # The dot product of document and query vectors will yield the full BM25 score.
                # Document vector contains the weighted term, query vector contains term frequency.
                indices.append(self.vocab[term])
                values.append(float(count))
                
        return {"indices": indices, "values": values}

    def save(self, path: str) -> None:
        """
        Serialize and save the inner BM25 model and vocabulary.
        
        Args:
            path: Target file path.
        """
        if self.bm25 is None:
            raise ValueError("Model has not been fitted, cannot save.")
            
        with open(path, "wb") as f:
            pickle.dump({"bm25": self.bm25, "vocab": self.vocab}, f)

    @classmethod
    def load(cls, path: str) -> "BM25Encoder":
        """
        Load a trained BM25Encoder from disk.
        
        Args:
            path: Path to the saved model pickle file.
            
        Returns:
            A fitted BM25Encoder instance.
        """
        with open(path, "rb") as f:
            data = pickle.load(f)
            
        encoder = cls()
        encoder.bm25 = data["bm25"]
        encoder.vocab = data.get("vocab", {})
        
        # Backward compatibility in case we loaded an older dump structure
        if not encoder.vocab and hasattr(encoder.bm25, 'idf'):
            encoder.vocab = {term: idx for idx, term in enumerate(encoder.bm25.idf.keys())}
            
        return encoder
