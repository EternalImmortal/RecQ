#coding:utf8
from baseclass.DeepRecommender import DeepRecommender
from random import choice
import tensorflow as tf
import numpy as np
from math import sqrt
class NGCF(DeepRecommender):

    def __init__(self,conf,trainingSet=None,testSet=None,fold='[1]'):
        super(NGCF, self).__init__(conf,trainingSet,testSet,fold)

    def next_batch(self):
        batch_id = 0
        while batch_id < self.train_size:
            if batch_id + self.batch_size <= self.train_size:
                users = [self.data.trainingData[idx][0] for idx in range(batch_id, self.batch_size + batch_id)]
                items = [self.data.trainingData[idx][1] for idx in range(batch_id, self.batch_size + batch_id)]
                batch_id += self.batch_size
            else:
                users = [self.data.trainingData[idx][0] for idx in range(batch_id, self.train_size)]
                items = [self.data.trainingData[idx][1] for idx in range(batch_id, self.train_size)]
                batch_id = self.train_size

            u_idx, i_idx, j_idx = [], [], []
            item_list = self.data.item.keys()
            for i, user in enumerate(users):

                i_idx.append(self.data.item[items[i]])
                u_idx.append(self.data.user[user])

                neg_item = choice(item_list)
                while neg_item in self.data.trainSet_u[user]:
                    neg_item = choice(item_list)
                j_idx.append(self.data.item[neg_item])

            yield u_idx, i_idx, j_idx

    def initModel(self):
        super(NGCF, self).initModel()

        ego_embeddings = tf.concat([self.user_embeddings,self.item_embeddings], axis=0)

        indices = [[self.data.user[item[0]],self.num_users+self.data.item[item[1]]] for item in self.data.trainingData]
        indices += [self.num_users+[self.data.item[item[1]],self.data.user[item[0]]] for item in self.data.trainingData]
        values = [self.data.trainingData[item[2]/sqrt(len(self.data.trainSet_u[item[0]]))/
                                         sqrt(len(self.data.trainSet_i[item[1]]))] for item in self.data.trainingData]*2

        norm_adj = tf.SparseTensor(indices=indices, values=values, dense_shape=[self.num_users+self.num_items,self.num_items+self.num_items])

        self.weights = dict()

        initializer = tf.contrib.layers.xavier_initializer()
        weight_size = [self.embed_size*4,self.embed_size*2,self.embed_size]
        weight_size_list = [self.embed_size] + weight_size

        self.n_layers = 3

        #initialize parameters
        for k in range(self.n_layers):
            self.weights['W_%d_1' % k] = tf.Variable(
                initializer([weight_size_list[k], weight_size_list[k + 1]]), name='W_%d_1' % k)
            self.weights['W_%d_2' % k] = tf.Variable(
                initializer([weight_size_list[k], weight_size_list[k + 1]]), name='W_%d_2' % k)

        all_embeddings = [ego_embeddings]
        for k in range(self.n_layers):
            side_embeddings = tf.sparse_tensor_dense_matmul(norm_adj,ego_embeddings)
            sum_embeddings = tf.matmul(side_embeddings+ego_embeddings, self.weights['W_%d_1' % k])
            bi_embeddings = tf.multiply(ego_embeddings, side_embeddings)
            bi_embeddings = tf.matmul(bi_embeddings, self.weights['W_%d_2' % k])

            ego_embeddings = tf.nn.leaky_relu(sum_embeddings+bi_embeddings)

            # message dropout.
            ego_embeddings = tf.nn.dropout(ego_embeddings, rate=0.1)

            # normalize the distribution of embeddings.
            norm_embeddings = tf.math.l2_normalize(ego_embeddings, axis=1)

            all_embeddings += [norm_embeddings]

        all_embeddings = tf.concat(all_embeddings, 1)
        self.multi_user_embeddings, self.multi_item_embeddings = tf.split(all_embeddings, [self.num_users, self.num_items], 0)


    def buildModel(self):
        init = tf.global_variables_initializer()
        self.sess.run(init)

        print 'training... (NeuMF)'
        for iteration in range(self.maxIter/5):
            for num, batch in enumerate(self.next_batch()):
                user_idx, item_idx, r = batch
                _, loss, y_neu = self.sess.run([self.neu_optimizer, self.neu_loss, self.y_neu],
                                          feed_dict={self.u_idx: user_idx, self.i_idx: item_idx, self.r: r})
                print 'iteration:', iteration, 'batch:', num, 'loss:', loss

    def predictForRanking(self, u):
        'invoked to rank all the items for the user'
        if self.data.containsUser(u):
            u = self.data.user[u]
            return self.predict_neu(u)
        else:
            return [self.data.globalMean] * self.num_items