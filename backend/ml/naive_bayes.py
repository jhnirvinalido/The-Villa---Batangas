"""Multinomial Naive Bayes with count and TF-IDF features.

The default word analyzer uses Unicode unigrams and bigrams. The TF-IDF model
also supports character n-grams; tokenization preserves negations and Taglish.
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

def features(text, ngram_range=(1,2)):
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?",unicodedata.normalize('NFKC',str(text)).casefold(),flags=re.UNICODE)
    return Counter(term for n in range(ngram_range[0],ngram_range[1]+1)
                   for i in range(len(words)-n+1)
                   for term in [' '.join(words[i:i+n])])

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
    def __init__(self, analyzer='word', word_ngram_range=(1,2),
                 char_ngram_range=(3,5), alpha=1.0,
                 class_prior_adjustment=None, neutral_oversample=1):
        if analyzer not in {'word', 'char'}:
            raise ValueError('Analyzer must be word or char.')
        if (len(word_ngram_range) != 2 or word_ngram_range[0] < 1
                or word_ngram_range[0] > word_ngram_range[1]):
            raise ValueError('Word n-gram range must contain positive, increasing bounds.')
        if (len(char_ngram_range) != 2 or char_ngram_range[0] < 1
                or char_ngram_range[0] > char_ngram_range[1]):
            raise ValueError('Character n-gram range must contain positive, increasing bounds.')
        self.analyzer = analyzer
        self.word_ngram_range = tuple(word_ngram_range)
        self.char_ngram_range = tuple(char_ngram_range)
        self.alpha=1.0
        self.class_prior_adjustment={label:1.0 for label in LABELS}
        self.neutral_oversample=1
        self._set_parameters(alpha,class_prior_adjustment,neutral_oversample)

    def _set_parameters(self,alpha,class_prior_adjustment,neutral_oversample):
        if not math.isfinite(alpha) or alpha <= 0:
            raise ValueError('Smoothing alpha must be a finite positive number.')
        if (isinstance(neutral_oversample, bool) or not isinstance(neutral_oversample, int)
                or neutral_oversample < 1):
            raise ValueError('Neutral oversampling must be a positive integer.')
        adjustments=class_prior_adjustment or {}
        if set(adjustments)-set(LABELS):
            raise ValueError('Class-prior adjustments may only name supported sentiment labels.')
        parsed={label:float(adjustments.get(label,1.0)) for label in LABELS}
        if any(not math.isfinite(value) or value<=0 for value in parsed.values()):
            raise ValueError('Class-prior adjustments must be finite positive multipliers.')
        self.alpha=float(alpha)
        self.class_prior_adjustment=parsed
        self.neutral_oversample=neutral_oversample
        if hasattr(self,'_feature_counts'):
            self._refresh_probabilities()

    def _refresh_probabilities(self):
        adjusted_priors={label:self._documents[label]*self.class_prior_adjustment[label]
                         for label in LABELS}
        prior_total=sum(adjusted_priors.values())
        self.prior={label:math.log(adjusted_priors[label]/prior_total) for label in LABELS}
        self.likelihood={}
        for label in LABELS:
            multiplier=self.neutral_oversample if label=='neutral' else 1
            weighted_total=sum(self._feature_counts[label].values())*multiplier
            self.likelihood[label]={
                term:math.log((self._feature_counts[label][term]*multiplier+self.alpha)/
                              (weighted_total+self.alpha*len(self.vocabulary)))
                for term in self.vocabulary
            }

    def terms(self, text):
        from .preprocessing import normalize
        text = normalize(text)
        if self.analyzer == 'word':
            return features(text, self.word_ngram_range)
        padded = ' ' + text + ' '
        return Counter(padded[i:i+n]
                       for n in range(self.char_ngram_range[0], self.char_ngram_range[1]+1)
                       for i in range(max(0,len(padded)-n+1)))

    def transform(self, text):
        return self._transform_terms(self.terms(text))

    def _transform_terms(self, terms):
        weights = {term: (1+math.log(count))*self.idf[term] for term,count in terms.items() if term in self.idf}
        norm = math.sqrt(sum(value*value for value in weights.values())) or 1
        return {term: value/norm for term,value in weights.items()}

    def fit(self, texts, labels):
        if not texts or len(texts) != len(labels) or set(labels) != set(LABELS):
            raise ValueError('Training requires all three sentiment classes.')
        df = Counter()
        terms_by_text=[self.terms(text) for text in texts]
        for terms in terms_by_text: df.update(set(terms))
        if not df: raise ValueError('Training text contains no usable features.')
        self.idf = {term: math.log((1+len(texts))/(1+count))+1 for term,count in df.items()}
        self.vocabulary = sorted(self.idf)
        self._documents=Counter(labels)
        self._feature_counts={label:Counter() for label in LABELS}
        for terms,label in zip(terms_by_text,labels):
            self._feature_counts[label].update(self._transform_terms(terms))
        self._refresh_probabilities()
        return self

    def predict_one(self, text):
        weights = self.transform(text)
        raw = {label: self.prior[label]+sum(weight*self.likelihood[label][term] for term,weight in weights.items()) for label in LABELS}
        peak = max(raw.values()); denominator = sum(math.exp(value-peak) for value in raw.values())
        scores = {label: math.exp(raw[label]-peak)/denominator for label in LABELS}
        return {'label': max(scores,key=scores.get), 'scores': scores, 'known_feature_occurrences': len(weights)}

    def to_dict(self):
        return {
            **super().to_dict(), 'kind': 'tfidf_nb', 'analyzer': self.analyzer, 'idf': self.idf,
            'word_ngram_range': list(self.word_ngram_range),
            'char_ngram_range': list(self.char_ngram_range), 'alpha': self.alpha,
            'class_prior_adjustment': self.class_prior_adjustment,
            'neutral_oversample': self.neutral_oversample,
        }

    @classmethod
    def from_dict(cls, data):
        model = cls(
            data['analyzer'],
            word_ngram_range=tuple(data.get('word_ngram_range', (1,2))),
            char_ngram_range=tuple(data.get('char_ngram_range', (3,5))),
            alpha=data.get('alpha', 1.0),
            class_prior_adjustment=data.get('class_prior_adjustment'),
            neutral_oversample=data.get('neutral_oversample', 1),
        )
        model.vocabulary = data['vocabulary']; model.idf = data['idf']
        model.prior = data['log_prior']; model.likelihood = data['log_likelihood']
        return model
