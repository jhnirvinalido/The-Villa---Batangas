"""Multinomial Naive Bayes with count features and Laplace smoothing.

Features are Unicode word unigrams and bigrams. Tokenization preserves
negations and Taglish words; no spelling correction or sentiment rules are used.
"""
import math
import re
import unicodedata
from collections import Counter

LABELS = ('negative','neutral','positive')

def rating_label(rating):
    text = str(rating).strip()
    if text not in {'1','2','3','4','5'}:
        raise ValueError('Star ratings must be integers from 1 to 5.')
    value = int(text)
    return 'negative' if value<=2 else 'neutral' if value==3 else 'positive'

def features(text):
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?",unicodedata.normalize('NFKC',str(text)).casefold(),flags=re.UNICODE)
    return Counter(words + [a+' '+b for a,b in zip(words,words[1:])])

class MultinomialNB:
    def fit(self,texts,labels):
        if not texts or len(texts)!=len(labels) or set(labels)!=set(LABELS):
            raise ValueError('Training requires text and examples from all three sentiment classes.')
        documents=Counter(labels)
        counts={label:Counter() for label in LABELS}
        for text,label in zip(texts,labels):counts[label].update(features(text))
        self.vocabulary=sorted(set().union(*(set(counts[label]) for label in LABELS)))
        if not self.vocabulary:raise ValueError('Training text contains no usable words.')
        self.prior={label:math.log(documents[label]/len(labels)) for label in LABELS}
        self.likelihood={label:{term:math.log((counts[label][term]+1)/(sum(counts[label].values())+len(self.vocabulary))) for term in self.vocabulary} for label in LABELS}
        return self
    def predict_one(self,text):
        terms=features(text)
        known=sum(count for term,count in terms.items() if term in self.likelihood[LABELS[0]])
        raw={label:self.prior[label]+sum(count*self.likelihood[label][term] for term,count in terms.items() if term in self.likelihood[label]) for label in LABELS}
        peak=max(raw.values());denominator=sum(math.exp(value-peak) for value in raw.values())
        scores={label:math.exp(raw[label]-peak)/denominator for label in LABELS}
        # These posterior scores are not calibrated confidence estimates.
        return {'label':max(scores,key=scores.get),'scores':scores,'known_feature_occurrences':known}
    def to_dict(self):
        return {'vocabulary':self.vocabulary,'log_prior':self.prior,'log_likelihood':self.likelihood}
    @classmethod
    def from_dict(cls,data):
        model=cls();model.vocabulary=data['vocabulary'];model.prior=data['log_prior'];model.likelihood=data['log_likelihood'];return model

class TfidfNB(MultinomialNB):
    """Multinomial NB over nonnegative L2-normalized TF-IDF, fit per partition."""
    def __init__(self, analyzer='word'):
        if analyzer not in {'word', 'char'}:
            raise ValueError('Analyzer must be word or char.')
        self.analyzer = analyzer

    def terms(self, text):
        from .preprocessing import normalize
        text = normalize(text)
        if self.analyzer == 'word':
            return features(text)
        padded = ' ' + text + ' '
        return Counter(padded[i:i+n] for n in (3,4,5) for i in range(max(0,len(padded)-n+1)))

    def transform(self, text):
        terms = self.terms(text)
        weights = {term: (1+math.log(count))*self.idf[term] for term,count in terms.items() if term in self.idf}
        norm = math.sqrt(sum(value*value for value in weights.values())) or 1
        return {term: value/norm for term,value in weights.items()}

    def fit(self, texts, labels):
        if not texts or len(texts) != len(labels) or set(labels) != set(LABELS):
            raise ValueError('Training requires all three sentiment classes.')
        df = Counter()
        for text in texts: df.update(set(self.terms(text)))
        if not df: raise ValueError('Training text contains no usable features.')
        self.idf = {term: math.log((1+len(texts))/(1+count))+1 for term,count in df.items()}
        self.vocabulary = sorted(self.idf)
        documents = Counter(labels); counts = {label: Counter() for label in LABELS}
        for text,label in zip(texts,labels): counts[label].update(self.transform(text))
        self.prior = {label: math.log(documents[label]/len(labels)) for label in LABELS}
        self.likelihood = {label: {term: math.log((counts[label][term]+1)/(sum(counts[label].values())+len(self.vocabulary))) for term in self.vocabulary} for label in LABELS}
        return self

    def predict_one(self, text):
        weights = self.transform(text)
        raw = {label: self.prior[label]+sum(weight*self.likelihood[label][term] for term,weight in weights.items()) for label in LABELS}
        peak = max(raw.values()); denominator = sum(math.exp(value-peak) for value in raw.values())
        scores = {label: math.exp(raw[label]-peak)/denominator for label in LABELS}
        return {'label': max(scores,key=scores.get), 'scores': scores, 'known_feature_occurrences': len(weights)}

    def to_dict(self):
        return {**super().to_dict(), 'kind': 'tfidf_nb', 'analyzer': self.analyzer, 'idf': self.idf}

    @classmethod
    def from_dict(cls, data):
        model = cls(data['analyzer']); model.vocabulary = data['vocabulary']; model.idf = data['idf']
        model.prior = data['log_prior']; model.likelihood = data['log_likelihood']
        return model
