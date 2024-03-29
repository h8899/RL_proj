
import tensorflow as tf
from collections import deque
import numpy as np
import random

tf_summaries_list=[]

def res_block(x,trainable):

    x_shortcut=x

    conv1_W = tf.Variable(tf.random_normal([1, 1, 32, 32], stddev=0.15), trainable=trainable)
    x = tf.nn.conv2d(x, filter=conv1_W, strides=[1, 1, 1, 1], padding='SAME')
    x = tf.layers.batch_normalization(x)
    x = tf.nn.relu(x)

    conv2_W = tf.Variable(tf.random_normal([1, 1, 32, 32], stddev=0.15), trainable=trainable)
    x = tf.nn.conv2d(x, filter=conv2_W, strides=[1, 1, 1, 1], padding='SAME')
    x = tf.layers.batch_normalization(x)
    x=tf.add(x,x_shortcut)
    x = tf.nn.relu(x)

    return x


def build_predictor(inputs, predictor, nes_num,scope,trainable):
    with tf.name_scope(scope):
        if predictor == 'CNN':

            L=int(inputs.shape[2])
            N = int(inputs.shape[3])

            conv1_W = tf.Variable(tf.truncated_normal([1,L,N,32], stddev=0.15), trainable=trainable)
            layer = tf.nn.conv2d(inputs, filter=conv1_W, padding='VALID', strides=[1, 1, 1, 1])
            norm1 = tf.layers.batch_normalization(layer)
            x = tf.nn.relu(norm1)

            for _ in range(nes_num):
                x = res_block(x, trainable)

            conv3_W = tf.Variable(tf.random_normal([1, 1, 32, 32], stddev=0.15), trainable=trainable)
            conv3 = tf.nn.conv2d(x, filter=conv3_W, strides=[1, 1, 1, 1], padding='VALID')
            norm3 = tf.layers.batch_normalization(conv3)
            net = tf.nn.relu(norm3)

            net = tf.layers.flatten(net)
            print(tf.shape(net))
            print("HIEU")
            return net

def variables_summaries(var,name):
    mean=tf.reduce_mean(var)

    tf.summary.scalar(name+'_mean',mean)

    std=tf.sqrt(tf.reduce_mean(tf.square(var-mean)))
    tf.summary.scalar(name+'_stddev',std)

    tf.summary.histogram(name+'_histogram',var)


class StockActor:
    def __init__(self,sess,predictor,M,L,N,batch_size):

        #Initial hyperparaters
        self.tau=10e-3
        self.learning_rate=10e-4
        self.gamma=0.99
        self.batch_size=batch_size

        #Initial session
        self.sess=sess

        #Initial input shape
        self.M=M
        self.L=L
        self.N=N

        self.init_input()
        self.scopes=['online/actor','target/actor']
        self.inputs,self.out,self.previous_action=self.build_actor(predictor,self.scopes[0],True)
        self.target_inputs, self.target_out,self.target_previous_action=self.build_actor(predictor,self.scopes[1],False)

        self.init_op()

        self.action_gradient=tf.placeholder(tf.float32,[None]+[self.M])
        self.unnormalized_actor_gradients=tf.gradients(self.out,self.network_params,-self.action_gradient)
        self.actor_gradients =list(map(lambda x: tf.div(x, self.batch_size), self.unnormalized_actor_gradients))#self.unnormalized_actor_gradients#list(map(lambda x: tf.div(x, 64), self.unnormalized_actor_gradients))

        # Optimization Op
        global_step = tf.Variable(0, trainable=False)
        #learning_rate = tf.train.exponential_decay(self.learning_rate, global_step,
                                                   # decay_steps=2000,
                                                   # decay_rate=0.95, staircase=False)
        self.optimize = tf.train.AdamOptimizer(self.learning_rate).apply_gradients(zip(self.actor_gradients, self.network_params),global_step=global_step)

        self.precise_action = tf.placeholder(tf.float32, [None]+[self.M])
        self.pre_loss=tf.reduce_sum(tf.square((self.precise_action-self.out)))

        #pre_train_learning_rate = tf.train.exponential_decay(10e-4, global_step,decay_steps=2000,decay_rate=0.95, staircase=False)
        self.pre_optimize=tf.train.AdamOptimizer(10e-3).minimize(self.pre_loss,global_step=global_step)
        self.num_trainable_vars = len(self.network_params) + len(self.traget_network_params)

    def init_input(self):
        self.r=tf.placeholder(tf.float32,[None]+[1])

    def init_op(self):
        #update op
        params=[tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES,scope) for scope in self.scopes]
        self.network_params=params[0]
        self.traget_network_params=params[1]
        params=zip(params[0],params[1])
        self.update=[tf.assign(t_a,(1-self.tau)*t_a+self.tau*p_a) for p_a,t_a in params]


    def build_actor(self,predictor,scope,trainable):
        with tf.name_scope(scope):
            inputs=tf.placeholder(tf.float32,shape=[None]+[self.M]+[self.L]+[self.N],name='input')
            x=build_predictor(inputs,predictor,1,scope,trainable=trainable)
            actions_previous=tf.placeholder(tf.float32,shape=[None]+[self.M])

            t1_w = tf.Variable(tf.truncated_normal([int(x.shape[1]), 32], stddev=0.15), name='t1_w')
            t1_b = tf.Variable(tf.constant(0.0, shape=[32]), name='t1_b')
            t1=tf.matmul(x,t1_w)+t1_b
            #t1=tf.nn.dropout(t1, keep_prob=0.1)

            t2_w = tf.Variable(tf.truncated_normal([int(actions_previous.shape[1]), 32], stddev=0.15))
            t2_b = tf.Variable(tf.constant(0.0, shape=[32]))
            t2 = tf.matmul(actions_previous, t2_w) + t2_b
            #t2=tf.nn.dropout(t2, keep_prob=0.1)

            net = tf.add(t1, t2)
            w_init=tf.random_uniform_initializer(-0.003,0.003)
            out=tf.layers.dense(net,self.M,activation=tf.nn.softmax,kernel_initializer=w_init)

            return inputs,out,actions_previous

    def train(self,inputs,a_gradient,a_previous):
        self.sess.run(self.optimize,feed_dict={self.inputs:inputs,self.action_gradient:a_gradient,self.previous_action:a_previous})

    def pre_train(self,s,a):
        pre_loss,_,_=self.sess.run([self.pre_loss,self.out,self.pre_optimize],feed_dict={self.inputs:s,self.precise_action:a})
        return pre_loss


    def predict(self,inputs,a_previous):
        return self.sess.run(self.out,feed_dict={self.inputs:inputs,self.previous_action:a_previous})

    def predict_target(self,inputs,target_previous_action):
        return self.sess.run(self.target_out,feed_dict={self.target_inputs:inputs,self.target_previous_action:target_previous_action})

    def update_target_network(self):
        self.sess.run(self.update)

class StockCritic:
    def __init__(self,sess,predictor,M,L,N):
        #Initial hyperparaters
        self.tau=10e-3
        self.learning_rate=10e-4
        self.gamma=0.99

        #Initial session
        self.sess=sess

        #Initial input shape
        self.M=M
        self.L=L
        self.N=N

        self.scopes=['online/critic','target/critic']
        self.target_inputs, self.target_actions, self.target_out,self.target_previous_action = self.build_critic(predictor,self.scopes[1],False)
        self.inputs,self.actions,self.out,self.previous_action=self.build_critic(predictor,self.scopes[0],True)



        self.init_op()

        self.predicted_q_value=tf.placeholder(tf.float32,[None,1])
        self.loss=tf.losses.mean_squared_error(self.predicted_q_value,self.out)

        # Optimization Op
        global_step = tf.Variable(0, trainable=False)
        learning_rate = tf.train.exponential_decay(self.learning_rate, global_step,
                                                   decay_steps=1000,
                                                   decay_rate=0.90, staircase=False)

        self.optimize = tf.train.GradientDescentOptimizer(self.learning_rate).minimize(self.loss,global_step=global_step)

        self.action_grads=tf.gradients(self.out,self.actions)


    def init_op(self):
        #update op
        params=[tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES,scope) for scope in self.scopes]
        self.network_params = params[0]
        self.traget_network_params = params[1]
        params=zip(params[0],params[1])
        self.update=[tf.assign(t_a,(1-self.tau)*t_a+self.tau*p_a) for p_a,t_a in params]



    def build_critic(self,predictor,scope,trainable):
        with tf.name_scope(scope):
            states=tf.placeholder(tf.float32,shape=[None]+[self.M,self.L,self.N])
            actions=tf.placeholder(tf.float32,shape=[None]+[self.M])
            actions_previous=tf.placeholder(tf.float32,shape=[None]+[self.M])
            net = build_predictor(states, predictor,5,scope,trainable)

            t1_w=tf.Variable(tf.truncated_normal([int(net.shape[1]),64],stddev=0.15))
            t1_b=tf.Variable(tf.constant(0.0,shape=[64]))
            t1=tf.matmul(net,t1_w)+t1_b
            t1=tf.nn.dropout(t1, keep_prob=0.2)


            t2_w = tf.Variable(tf.truncated_normal([int(actions.shape[1]), 64], stddev=0.15))
            t2_b = tf.Variable(tf.constant(0.0, shape=[64]))
            t2 = tf.matmul(actions, t2_w) + t2_b
            t2=tf.nn.dropout(t2, keep_prob=0.2)


            t3_w = tf.Variable(tf.truncated_normal([int(actions.shape[1]), 64], stddev=0.15))
            t3_b = tf.Variable(tf.constant(0.0, shape=[64]))
            t3 = tf.matmul(actions_previous, t3_w) + t3_b

            net = tf.add(t1, t2)
            net = tf.add(net, t3)
            net=tf.layers.batch_normalization(net)


            net = tf.nn.relu(net)
            net=tf.nn.dropout(net,keep_prob=0.5)

            out = tf.layers.dense(net, 1, kernel_initializer=tf.random_uniform_initializer(-0.003, 0.003))

        return states,actions,out,actions_previous

    def train(self,inputs,actions,predicted_q_value,a_previous):
        critic_loss,q_value,_=self.sess.run([self.loss,self.out,self.optimize],feed_dict={self.inputs:inputs,self.actions:actions,self.predicted_q_value:predicted_q_value,self.previous_action:a_previous})
        return critic_loss,q_value

    def predict(self,inputs,actions):
        return self.sess.run(self.out,feed_dict={self.inputs:inputs,self.actions:actions})

    def preditc_target(self,inputs,actions,a_previous):
        return self.sess.run(self.target_out,feed_dict={self.target_inputs:inputs,self.target_actions:actions,self.target_previous_action:a_previous})

    def update_target_network(self):
        self.sess.run(self.update)

    def action_gradients(self,inputs,actions,a_previous):
        return self.sess.run(self.action_grads,feed_dict={self.inputs:inputs,self.actions:actions,self.previous_action:a_previous})

class StockCriticAugmented:
    def __init__(self,sess,predictor,M,L,N):
        #Initial hyperparaters
        self.tau=10e-3
        self.learning_rate=10e-4
        self.gamma=0.99
        self.a = 0.5

        #Initial session
        self.sess=sess

        #Initial input shape
        self.M=M
        self.L=L
        self.N=N

        self.scopes=['online/critic_augmented','target/critic_augmented']
        self.target_inputs, self.target_actions, self.target_out,self.target_previous_action = self.build_critic_augmented(predictor,self.scopes[1],False)
        self.inputs,self.actions,self.out,self.previous_action=self.build_critic_augmented(predictor,self.scopes[0],True)


        self.init_op()

        self.predicted_q_value=tf.placeholder(tf.float32,[None,1])
        self.loss=tf.losses.mean_squared_error(self.predicted_q_value,self.out)

        # Optimization Op
        global_step = tf.Variable(0, trainable=False)
        learning_rate = tf.train.exponential_decay(self.learning_rate, global_step,
                                                   decay_steps=1000,
                                                   decay_rate=0.90, staircase=False)

        self.optimize = tf.train.GradientDescentOptimizer(self.learning_rate).minimize(self.loss,global_step=global_step)

        self.action_grads=tf.gradients(self.out,self.actions)


    def init_op(self):
        #update op
        params=[tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES,scope) for scope in self.scopes]
        self.network_params = params[0]
        self.traget_network_params = params[1]
        params=zip(params[0],params[1])
        self.update=[tf.assign(t_a,(1-self.tau)*t_a+self.tau*p_a) for p_a,t_a in params]



    def build_critic_augmented(self,predictor,scope,trainable):
        with tf.name_scope(scope):
            states=tf.placeholder(tf.float32,shape=[None]+[self.M,self.L,self.N])
            actions=tf.placeholder(tf.float32,shape=[None]+[self.M])
            actions_previous=tf.placeholder(tf.float32,shape=[None]+[self.M])
            net = build_predictor(states, predictor,5,scope,trainable)

            t1_w=tf.Variable(tf.truncated_normal([int(net.shape[1]),64],stddev=0.15))
            t1_b=tf.Variable(tf.constant(0.0,shape=[64]))
            t1=tf.matmul(net,t1_w)+t1_b
            t1=tf.nn.dropout(t1, keep_prob=0.2)


            t2_w = tf.Variable(tf.truncated_normal([int(actions.shape[1]), 64], stddev=0.15))
            t2_b = tf.Variable(tf.constant(0.0, shape=[64]))
            t2 = tf.matmul(actions, t2_w) + t2_b
            t2=tf.nn.dropout(t2, keep_prob=0.2)


            t3_w = tf.Variable(tf.truncated_normal([int(actions.shape[1]), 64], stddev=0.15))
            t3_b = tf.Variable(tf.constant(0.0, shape=[64]))
            t3 = tf.matmul(actions_previous, t3_w) + t3_b

            net = tf.add(t1, t2)
            net = tf.add(net, t3)
            net=tf.layers.batch_normalization(net)


            net = tf.nn.relu(net)
            net=tf.nn.dropout(net,keep_prob=0.5)

            out = tf.layers.dense(net, 1, kernel_initializer=tf.random_uniform_initializer(-0.003, 0.003))

        return states,actions,out,actions_previous

    def train(self,inputs,actions,predicted_q_value,a_previous):
        critic_loss,q_value,_=self.sess.run([self.loss,self.out,self.optimize],feed_dict={self.inputs:inputs,self.actions:actions,self.predicted_q_value:predicted_q_value,self.previous_action:a_previous})
        return critic_loss,q_value

    def predict(self,inputs,actions):
        return self.sess.run(self.out,feed_dict={self.inputs:inputs,self.actions:actions})

    def preditc_target(self,inputs,actions,a_previous):
        return self.sess.run(self.target_out,feed_dict={self.target_inputs:inputs,self.target_actions:actions,self.target_previous_action:a_previous})

    def update_target_network(self):
        self.sess.run(self.update)

    def action_gradients(self,inputs,actions,a_previous):
        return self.sess.run(self.action_grads,feed_dict={self.inputs:inputs,self.actions:actions,self.previous_action:a_previous})


def  build_summaries():
    critic_loss=tf.Variable(0.)
    reward=tf.Variable(0.)
    ep_ave_max_q=tf.Variable(0.)
    actor_loss=tf.Variable(0.)
    tf.summary.scalar('Critic_loss',critic_loss)
    tf.summary.scalar('Reward',reward)
    tf.summary.scalar('Ep_ave_max_q',ep_ave_max_q)
    tf.summary.scalar('Actor_loss',actor_loss)


    summary_vars=[critic_loss,reward,ep_ave_max_q,actor_loss]
    summary_ops=tf.summary.merge_all()
    return summary_ops,summary_vars



class GPDP:
    def __init__(self,predictor,M,L,N,name,load_weights,trainable):
        # Initial buffer
        self.buffer = list()
        self.buffer2 = list()
        self.buffer_size = 100
        self.batch_size = 32
        self.name=name
        self.factor = 0.25
        #Build up models
        self.sesson = tf.Session()
        self.actor=StockActor(self.sesson,predictor,M,L,N,self.batch_size)
        self.critic=StockCritic(self.sesson,predictor,M,L,N)
        self.critic_augmented = StockCriticAugmented(self.sesson, predictor, M,L,N)

        #Initial Hyperparameters
        self.gamma=0.99

        #Initial saver
        self.saver=tf.train.Saver(max_to_keep=10)

        if load_weights=='True':
            print("Loading Model")
            try:
                checkpoint = tf.train.get_checkpoint_state('./saved_network/GPDP')
                if checkpoint and checkpoint.model_checkpoint_path:
                    self.saver.restore(self.sesson, checkpoint.model_checkpoint_path)
                    print("Successfully loaded:", checkpoint.model_checkpoint_path)
                else:
                    print("Could not find old network weights")
                    self.sesson.run(tf.global_variables_initializer())
            except:
                print("Could not find old network weights")
                self.sesson.run(tf.global_variables_initializer())
        else:
            self.sesson.run(tf.global_variables_initializer())

        if trainable=='True':
            # Initial summary
            self.summary_writer = tf.summary.FileWriter('./summary/GPDP', self.sesson.graph)
            self.summary_ops, self.summary_vars = build_summaries()

    #online actor
    def predict(self,s,a_previous):
        return self.actor.predict(s,a_previous)

    #target actor
    # def test_predict(self,s):
    #     return self.actor.predict_target(s)

    def save_transition(self,s,w,r,not_terminal,s_next, action_previous, typeCritic):
        if(typeCritic=='original'):
            if len(self.buffer)>self.buffer_size:
                self.buffer.pop(0)
            self.buffer.append((s,w[0],r,not_terminal,s_next,action_previous))
        elif(typeCritic=='augmented'):
            if len(self.buffer2)>self.buffer_size:
                self.buffer2.pop(0)
            self.buffer2.append((s,w[0],r,not_terminal,s_next,action_previous))

    def train(self,method,epoch):
        info = dict()
        if len(self.buffer)<self.buffer_size:
            info["critic_loss"],info["q_value"],info["actor_loss"]= 0,0,0
            return info
        ##
        s,a,r,not_terminal,s_next,a_previous=self.get_transition_batch('augmented')
        target_q_augmented=self.critic_augmented.preditc_target(s_next,self.actor.predict_target(s_next,a_previous),a_previous)

        y_i_augmented=[]
        for i in range(self.batch_size):
                y_i_augmented.append(r[i]+not_terminal[i]*self.gamma*target_q_augmented[i])

        critic_loss_augmented,q_value_augmented=self.critic_augmented.train(s,a,np.reshape(y_i_augmented,(-1,1)),a_previous)
        ##
        s,a,r,not_terminal,s_next,a_previous=self.get_transition_batch('original')
        target_q=self.critic.preditc_target(s_next,self.actor.predict_target(s_next,a_previous),a_previous)

        y_i=[]
        for i in range(self.batch_size):
                y_i.append(r[i]+not_terminal[i]*self.gamma*target_q[i])

        critic_loss,q_value=self.critic.train(s,a,np.reshape(y_i,(-1,1)),a_previous)
        ##
        info["critic_loss"]=critic_loss
        info["q_value"]=np.amax(q_value)

        if method=='model_free':
            a_outs = self.actor.predict(s,a_previous)
            grads = self.critic.action_gradients(s, a_outs,a_previous)
            grads2 = self.critic_augmented.action_gradients(s, a_outs, a_previous)
            grads_total = np.array(grads[0]) * (1-self.factor) + np.array(grads2[0]) * self.factor
            self.actor.train(s,grads_total,a_previous)
        elif method=='model_based':
            if epoch<=100:
                actor_loss=self.actor.pre_train(s, a_previous)
                info["actor_loss"]=actor_loss
            else:
                a_outs = self.actor.predict(s,a_previous)
                grads = self.critic.action_gradients(s, a_outs,a_previous)
                grads2 = self.critic_augmented.action_gradients(s, a_outs, a_previous)
                grads_total = np.array(grads[0]) * (1-self.factor) + np.array(grads2[0]) * self.factor
                self.actor.train(s,grads_total,a_previous)


        self.actor.update_target_network()
        self.critic.update_target_network()
        self.critic_augmented.update_target_network()
        return info


    def get_transition_batch(self, typeCritic):
        if(typeCritic == 'original'):
            minibatch = random.sample(self.buffer, self.batch_size)
        elif(typeCritic == 'augmented'):
            minibatch = random.sample(self.buffer2, self.batch_size)
        s = [data[0][0] for data in minibatch]
        a = [data[1] for data in minibatch]
        r = [data[2] for data in minibatch]
        not_terminal = [data[3] for data in minibatch]
        s_next = [data[4][0] for data in minibatch]
        action_previous=[data[5][0] for data in minibatch]
        return s, a, r, not_terminal, s_next,action_previous


    def save_model(self,epoch):
        self.saver.save(self.sesson,'./saved_network/GPDP/'+self.name,global_step=epoch)

    def write_summary(self,Loss,reward,ep_ave_max_q,actor_loss,epoch):
        summary_str = self.sesson.run(self.summary_ops, feed_dict={
            self.summary_vars[0]: Loss,
            self.summary_vars[1]: reward,
            self.summary_vars[2]: ep_ave_max_q,
            self.summary_vars[3]: actor_loss
        })
        self.summary_writer.add_summary(summary_str, epoch)

    def reset_buffer(self):
        self.buffer = list()
