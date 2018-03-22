#
"""
Paired text data that consists of source text and target text.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import copy

import tensorflow as tf

from texar.core import utils
from texar.data.data.mono_text_data import _default_mono_text_dataset_hparams
from texar.data.data.text_data_base import TextDataBase
from texar.data.data.mono_text_data import MonoTextData
from texar.data.data import data_utils
from texar.data.vocabulary import Vocab
from texar.data.embedding import Embedding
from texar.data.constants import BOS_TOKEN, EOS_TOKEN

# pylint: disable=invalid-name, arguments-differ, not-context-manager
# pylint: disable=protected-access

__all__ = [
    "_default_paired_text_dataset_hparams",
    "PairedTextData"
]

def _default_paired_text_dataset_hparams():
    """Returns hyperparameters of a mono text dataset with default values.
    """
    # TODO(zhiting): add more docs
    source_hparams = _default_mono_text_dataset_hparams()
    source_hparams["bos_token"] = None
    source_hparams["data_name"] = "source"
    target_hparams = _default_mono_text_dataset_hparams()
    target_hparams.update(
        {
            "vocab_share": False,
            "embedding_init_share": False,
            "processing_share": False,
            "data_name": "target"
        }
    )
    return {
        "source_dataset": source_hparams,
        "target_dataset": target_hparams
    }

# pylint: disable=too-many-instance-attributes, too-many-public-methods
class PairedTextData(TextDataBase):
    """Text data base that reads source and target text.

    This is for the use of, e.g., seq2seq models.

    Args:
        hparams (dict): Hyperparameters. See :meth:`default_hparams` for the
            defaults.
    """
    def __init__(self, hparams):
        TextDataBase.__init__(self, hparams)
        with tf.name_scope(self.name, self.default_hparams()["name"]):
            self._make_data()

    @staticmethod
    def default_hparams():
        """Returns a dicitionary of default hyperparameters.
        """
        hparams = TextDataBase.default_hparams()
        hparams["name"] = "paired_text_data"
        hparams.update(_default_paired_text_dataset_hparams())
        return hparams

    @staticmethod
    def make_vocab(src_hparams, tgt_hparams):
        """Reads vocab files and returns source vocab and target vocab.

        Args:
            src_hparams (dict or HParams): Hyperparameters of source dataset.
            tgt_hparams (dict or HParams): Hyperparameters of target dataset.

        Returns:
            A pair of :class:`texar.data.Vocab` instances. The two instances
            may be the same objects if source and target vocabs are shared
            and have the same other configs.
        """
        src_vocab = MonoTextData.make_vocab(src_hparams)

        if tgt_hparams["processing_share"]:
            tgt_bos_token = src_hparams["bos_token"]
            tgt_eos_token = src_hparams["eos_token"]
        else:
            tgt_bos_token = tgt_hparams["bos_token"]
            tgt_eos_token = tgt_hparams["eos_token"]
        tgt_bos_token = utils.default_string(tgt_bos_token,
                                             BOS_TOKEN)
        tgt_eos_token = utils.default_string(tgt_eos_token,
                                             EOS_TOKEN)
        if tgt_hparams["vocab_share"]:
            if tgt_bos_token == src_vocab.bos_token and \
                    tgt_eos_token == src_vocab.eos_token:
                tgt_vocab = src_vocab
            else:
                tgt_vocab = Vocab(src_hparams["vocab_file"],
                                  bos_token=tgt_bos_token,
                                  eos_token=tgt_eos_token)
        else:
            tgt_vocab = Vocab(tgt_hparams["vocab_file"],
                              bos_token=tgt_bos_token,
                              eos_token=tgt_eos_token)

        return src_vocab, tgt_vocab


    @staticmethod
    def make_embedding(src_emb_hparams, src_token_to_id_map,
                       tgt_emb_hparams=None, tgt_token_to_id_map=None,
                       emb_init_share=False):
        """Optionally loads source and target embeddings from files
        (if provided), and returns respective :class:`texar.data.Embedding`
        instances.
        """
        src_embedding = MonoTextData.make_embedding(src_emb_hparams,
                                                    src_token_to_id_map)

        if emb_init_share:
            tgt_embedding = src_embedding
        else:
            tgt_emb_file = tgt_emb_hparams["file"]
            tgt_embedding = None
            if tgt_emb_file is not None and tgt_emb_file != "":
                tgt_embedding = Embedding(tgt_token_to_id_map, tgt_emb_hparams)

        return src_embedding, tgt_embedding

    def _make_dataset(self):
        src_dataset = tf.data.TextLineDataset(
            self._hparams.source_dataset.files,
            compression_type=self._hparams.source_dataset.compression_type)
        tgt_dataset = tf.data.TextLineDataset(
            self._hparams.target_dataset.files,
            compression_type=self._hparams.target_dataset.compression_type)
        return tf.data.Dataset.zip((src_dataset, tgt_dataset))

    @staticmethod
    def _get_name_prefix(src_hparams, tgt_hparams):
        name_prefix = [
            src_hparams["data_name"], tgt_hparams["data_name"]]
        if name_prefix[0] == name_prefix[1]:
            raise ValueError("'data_name' of source and target "
                             "datasets cannot be the same.")
        return name_prefix

    @staticmethod
    def _make_processor(src_hparams, tgt_hparams, data_spec, name_prefix=None):
        # Create source data decoder
        data_spec_i = data_spec.get_ith_data_spec(0)
        src_decoder, src_trans, data_spec_i = MonoTextData._make_processor(
            src_hparams, data_spec_i, chained=False)
        data_spec.set_ith_data_spec(0, data_spec_i, 2)

        # Create target data decoder
        tgt_proc_hparams = tgt_hparams
        if tgt_hparams["processing_share"]:
            tgt_proc_hparams = copy.copy(src_hparams)
            try:
                tgt_proc_hparams["variable_utterance"] = \
                        tgt_hparams["variable_utterance"]
            except TypeError:
                tgt_proc_hparams.variable_utterance = \
                        tgt_hparams["variable_utterance"]
        data_spec_i = data_spec.get_ith_data_spec(1)
        tgt_decoder, tgt_trans, data_spec_i = MonoTextData._make_processor(
            tgt_proc_hparams, data_spec_i, chained=False)
        data_spec.set_ith_data_spec(1, data_spec_i, 2)

        if not name_prefix:
            name_prefix = ["source", "target"]
        tran_fn = data_utils.make_combined_transformation(
            [[src_decoder] + src_trans, [tgt_decoder] + tgt_trans],
            name_prefix=name_prefix)

        data_spec.add_spec(name_prefix=name_prefix)

        return tran_fn, data_spec

    def _process_dataset(self, dataset, hparams, data_spec):
        name_prefix = PairedTextData._get_name_prefix(
            hparams["source_dataset"], hparams["target_dataset"])
        tran_fn, data_spec = self._make_processor(
            hparams["source_dataset"], hparams["target_dataset"],
            data_spec, name_prefix=name_prefix)
        num_parallel_calls = hparams["num_parallel_calls"]
        dataset = dataset.map(
            lambda *args: tran_fn(data_utils.maybe_tuple(args)),
            num_parallel_calls=num_parallel_calls)
        return dataset, data_spec

    def _make_length_fn(self):
        length_fn = self._hparams.bucket_length_fn
        if not length_fn:
            length_fn = lambda x: tf.maximum(
                x[self.source_length_name], x[self.target_length_name])
        elif not utils.is_callable(length_fn):
            # pylint: disable=redefined-variable-type
            length_fn = utils.get_function(length_fn, ["texar.custom"])
        return length_fn

    def _make_data(self):
        self._src_vocab, self._tgt_vocab = self.make_vocab(
            self._hparams.source_dataset, self._hparams.target_dataset)

        tgt_hparams = self._hparams.target_dataset
        if not tgt_hparams.vocab_share and tgt_hparams.embedding_init_share:
            raise ValueError("embedding_init can be shared only when vocab "
                             "is shared. Got `vocab_share=False, "
                             "emb_init_share=True`.")
        self._src_embedding, self._tgt_embedding = self.make_embedding(
            self._hparams.source_dataset.embedding_init,
            self._src_vocab.token_to_id_map_py,
            self._hparams.target_dataset.embedding_init,
            self._tgt_vocab.token_to_id_map_py,
            self._hparams.target_dataset.embedding_init_share)

        # Create dataset
        dataset = self._make_dataset()
        dataset, dataset_size = self._shuffle_dataset(
            dataset, self._hparams, self._hparams.source_dataset.files)
        self._dataset_size = dataset_size

        # Processing.
        data_spec = data_utils._DataSpec(
            dataset=dataset, dataset_size=self._dataset_size,
            vocab=[self._src_vocab, self._tgt_vocab],
            embedding=[self._src_embedding, self._tgt_embedding])
        dataset, data_spec = self._process_dataset(
            dataset, self._hparams, data_spec)
        self._data_spec = data_spec
        self._src_decoder = data_spec.decoder[0]
        self._tgt_decoder = data_spec.decoder[1]

        # Batching
        length_fn = self._make_length_fn()
        dataset = self._make_batch(dataset, self._hparams, length_fn)

        # Prefetching
        if self._hparams.prefetch_buffer_size > 0:
            dataset = dataset.prefetch(self._hparams.prefetch_buffer_size)

        self._dataset = dataset

    def list_items(self):
        """Returns the list of item names that the data can produce.

        Returns:
            A list of strings.
        """
        return list(self._dataset.output_types.keys())

    @property
    def dataset(self):
        """The dataset.
        """
        return self._dataset

    def dataset_size(self):
        """Returns the number of data instances in the dataset.
        """
        if not self._dataset_size:
            # pylint: disable=attribute-defined-outside-init
            self._dataset_size = data_utils.count_file_lines(
                self._hparams.source_dataset.files)
        return self._dataset_size

    @property
    def vocab(self):
        """A pair instances of :class:`~texar.data.Vocab` that are source
        and target vocabs, respectively.
        """
        return self._src_vocab, self._tgt_vocab

    @property
    def source_vocab(self):
        """The source vocab, an instance of :class:`~texar.data.Vocab`.
        """
        return self._src_vocab

    @property
    def target_vocab(self):
        """The target vocab, an instance of :class:`~texar.data.Vocab`.
        """
        return self._tgt_vocab

    @property
    def source_embedding_init_value(self):
        """The `Tensor` containing the embedding value of source data
        loaded from file. `None` if embedding is not specified.
        """
        if self._src_embedding is None:
            return None
        return self._src_embedding.word_vecs

    @property
    def target_embedding_init_value(self):
        """The `Tensor` containing the embedding value of target data
        loaded from file. `None` if embedding is not specified.
        """
        if self._tgt_embedding is None:
            return None
        return self._tgt_embedding.word_vecs

    def embedding_init_value(self):
        """A pair of `Tensor` containing the embedding values of source and
        target data loaded from file.
        """
        src_emb = self.source_embedding_init_value
        tgt_emb = self.target_embedding_init_value
        return src_emb, tgt_emb

    @property
    def source_text_name(self):
        """The name of the source text tensor.
        """
        return 'source_' + self._src_decoder.text_tensor_name

    @property
    def source_length_name(self):
        """The name of the source length tensor.
        """
        return 'source_' + self._src_decoder.length_tensor_name

    @property
    def source_text_id_name(self):
        """The name of the source text index tensor.
        """
        return 'source_' + self._src_decoder.text_id_tensor_name

    @property
    def source_utterance_cnt_name(self):
        """The name of the source text utterance count tensor.
        """
        if not self._hparams.source_dataset.variable_utterance:
            raise ValueError(
                "`utterance_cnt_name` of source data is undefined.")
        return 'source_' + self._src_decoder.utterance_cnt_tensor_name

    @property
    def target_text_name(self):
        """The name of the target text tensor.
        """
        return 'target_' + self._tgt_decoder.text_tensor_name

    @property
    def target_length_name(self):
        """The name of the target length tensor.
        """
        return 'target_' + self._tgt_decoder.length_tensor_name

    @property
    def target_text_id_name(self):
        """The name of the target text index tensor.
        """
        return 'target_' + self._tgt_decoder.text_id_tensor_name

    @property
    def target_utterance_cnt_name(self):
        """The name of the target text utterance count tensor.
        """
        if not self._hparams.target_dataset.variable_utterance:
            raise ValueError(
                "`utterance_cnt_name` of target data is undefined.")
        return 'target_' + self._tgt_decoder.utterance_cnt_tensor_name

    @property
    def text_name(self):
        """The name of text tensor.
        """
        return self._src_decoder.text_tensor_name

    @property
    def length_name(self):
        """The name of length tensor.
        """
        return self._src_decoder.length_tensor_name

    @property
    def text_id_name(self):
        """The name of text index tensor.
        """
        return self._src_decoder.text_id_tensor_name

    @property
    def utterance_cnt_name(self):
        """The name of the target text utterance count tensor.
        """
        if self._hparams.source_dataset.variable_utterance:
            return self._src_decoder.utterance_cnt_tensor_name
        if self._hparams.target_dataset.variable_utterance:
            return self._tgt_decoder.utterance_cnt_tensor_name
        raise ValueError("`utterance_cnt_name` is not defined.")
