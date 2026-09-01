import os
import jieba
from typing import List

# Read dictionary path from settings/environment, default to local dict.txt.big
_dict_path = os.getenv("JIEBA_DICT_PATH", os.path.join(os.path.dirname(__file__), "dict.txt.big"))

# Load custom Traditional Chinese dictionary if it exists
if os.path.exists(_dict_path):
    jieba.set_dictionary(_dict_path)

# Load stopwords
_stopwords_path = os.path.join(os.path.dirname(__file__), "stopwords_zh.txt")
_stopwords = set()
if os.path.exists(_stopwords_path):
    with open(_stopwords_path, "r", encoding="utf-8") as f:
        _stopwords = {line.strip() for line in f if line.strip()}

def tokenize_zh(text: str) -> List[str]:
    """
    Tokenize traditional Chinese text using jieba.
    
    Filters out:
    1. Stopwords defined in stopwords_zh.txt
    2. Tokens with length < 2
    3. Punctuation (returns pure text tokens)
    
    Args:
        text (str): Input Chinese text.
        
    Returns:
        List[str]: A list of cleaned tokens.
    """
    if not text:
        return []
        
    # Use jieba to cut the text
    cut_tokens = jieba.cut(text)
    
    tokens = []
    for token in cut_tokens:
        token = token.strip()
        
        # Check length
        if len(token) < 2:
            continue
            
        # Check stopword
        if token in _stopwords:
            continue
            
        # Ensure it contains purely text/alphanumeric characters, no punctuation
        # isalnum() returns True if all characters are alphanumeric (including CJK characters)
        if not token.isalnum():
            continue
                
        tokens.append(token)
        
    return tokens
