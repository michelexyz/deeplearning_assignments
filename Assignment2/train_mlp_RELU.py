from _context import vugrad

import numpy as np

# for running from the command line
from argparse import ArgumentParser

import vugrad as vg
from vugrad.core import Op


class MLP(vg.Module):
    """
    A simple MLP with one hidden layer, and a sigmoid non-linearity on the hidden layer and a softmax on the
    output.
    """

    def __init__(self, input_size, output_size, hidden_mult=4):
        """
        :param input_size:
        :param output_size:
        :param hidden_mult: Multiplier that indicates how many times bigger the hidden layer is than the input layer.
        """
        super().__init__()

        hidden_size = hidden_mult * input_size
        # -- There is no common wisdom on how big the hidden size should be, apart from the idea
        #    that it should be strictly _bigger_ than the input if at all possible.

        self.layer1 = vg.Linear(input_size, hidden_size)
        self.layer2 = vg.Linear(hidden_size, output_size)
        # -- The linear layer (without activation) is implemented in vugrad. We simply instantiate these modules, and
        #    add them to our network.

    def forward(self, input):

        assert len(input.size()) == 2

        # first layer
        hidden = self.layer1(input)

        # non-linearity
        hidden = vg.sigmoid(hidden)
        # -- We've called a utility function here, to mimin how this is usually done in pytorch. We could also do:
        #    hidden = Sigmoid.do_forward(hidden)

        # second layer
        output = self.layer2(hidden)

        # softmax activation
        output = vg.logsoftmax(output)
        # -- the logsoftmax computes the _logarithm_ of the probabilities produced by softmax. This makes the computation
        #    of the CE loss more stable when the probabilities get close to 0 (remember that the CE loss is the logarithm
        #    of these probabilities). It needs to be implemented in a specific way. See the source for details.

        return output

    def parameters(self):

        return self.layer1.parameters() + self.layer2.parameters()

## Define the ReLU activation function
class ReLU(Op):

    @staticmethod
    def forward(context, input):

        context['input'] = input

        return np.maximum(0, input)

    @staticmethod
    def backward(context, goutput):
        input = context['input']

        return (input > 0) * goutput

# Create a simple neural network.
# This is a `Module` consisting of other modules representing linear layers, provided by the vugrad library.
class MLPReLU(vg.Module):
    """
    A simple MLP with one hidden layer, and a sigmoid non-linearity on the hidden layer and a softmax on the
    output.
    """

    def __init__(self, input_size, output_size, hidden_mult=4):
        """
        :param input_size:
        :param output_size:
        :param hidden_mult: Multiplier that indicates how many times bigger the hidden layer is than the input layer.
        """
        super().__init__()

        hidden_size = hidden_mult * input_size
        # -- There is no common wisdom on how big the hidden size should be, apart from the idea
        #    that it should be strictly _bigger_ than the input if at all possible.

        self.layer1 = vg.Linear(input_size, hidden_size)
        self.layer2 = vg.Linear(hidden_size, output_size)
        # -- The linear layer (without activation) is implemented in vugrad. We simply instantiate these modules, and
        #    add them to our network.

    def forward(self, input):

        assert len(input.size()) == 2

        # first layer
        hidden = self.layer1(input)

        # non-linearity
        hidden = ReLU.do_forward(hidden)
        # second layer
        output = self.layer2(hidden)

        # softmax activation
        output = vg.logsoftmax(output)
        # -- the logsoftmax computes the _logarithm_ of the probabilities produced by softmax. This makes the computation
        #    of the CE loss more stable when the probabilities get close to 0 (remember that the CE loss is the logarithm
        #    of these probabilities). It needs to be implemented in a specific way. See the source for details.

        return output

    def parameters(self):

        return self.layer1.parameters() + self.layer2.parameters()




# define the training as a function that returns the accuracies and losses

def train_mlp(batch_size, epochs, lr, data_name, mlp_class):
    

    ## Load the data
    if data_name == 'synth':
        (xtrain, ytrain), (xval, yval), num_classes = vg.load_synth()
    elif data_name == 'mnist':
        (xtrain, ytrain), (xval, yval), num_classes = vg.load_mnist(final=False, flatten=True)
    else:
        raise Exception(f'Dataset {data_name} not recognized.')

    print(f'## loaded data:')
    print(f'         number of instances: {xtrain.shape[0]} in training, {xval.shape[0]} in validation')
    print(f' training class distribution: {np.bincount(ytrain)}')
    print(f'     val. class distribution: {np.bincount(yval)}')

    num_instances, num_features = xtrain.shape
    
    # instantiate the model

    mlp = mlp_class(input_size=num_features, output_size=num_classes)

    n, m = xtrain.shape

    b = batch_size

    val_accuracies = []

    train_losses = []

    print('\n## Starting training')

    for epoch in range(epochs):

        print(f'epoch {epoch:03}')

        ## Compute validation accuracy
        o = mlp(vg.TensorNode(xval))
        oval = o.value

        predictions = np.argmax(oval, axis=1)
        num_correct = (predictions == yval).sum()
        acc = num_correct / yval.shape[0]

        o.clear() # gc the computation graph
        print(f'       accuracy: {acc:.4}')

        val_accuracies.append(acc)


        cl = 0.0 # running sum of the training loss

        # We loop over the data in batches of size `b`
        for fr in range(0, n, b):

            # The end index of the batch
            to = min(fr + b, n)

            # Slice out the batch and its corresponding target values
            batch, targets = xtrain[fr:to, :], ytrain[fr:to]

            # Wrap the inputs in a Node
            batch = vg.TensorNode(value=batch)

            outputs = mlp(batch)
            loss = vg.logceloss(outputs, targets)
            # -- The computation graph is now complete. It consists of the MLP, together with the computation of
            #    the scalar loss.
            # -- The variable `loss` is the TensorNode at the very top of our computation graph. This means we can call
            #    it to perform operations on the computation graph, like clearing the gradients, starting the backpropgation
            #    and clearing the graph.
            # -- Note that we set the MLP up to produce log probabilties, so we should compute the CE loss for these.

            cl += loss.value
            # -- We must be careful here to extract the _raw_ value for the running loss. What would happen if we kept
            #    a running sum using the TensorNode?

            # Start the backpropagation
            loss.backward()

            # pply gradient descent
            for parm in mlp.parameters():
                parm.value -= lr * parm.grad
                # -- Note that we are directly manipulating the members of the parm TensorNode. This means that for this
                #    part, we are not building up a computation graph.

            # -- In Pytorch, the gradient descent is abstracted away into an Optimizer. This allows us to build slightly more
            #    complexoptimizers than plain graident descent.

            # Finally, we need to reset the gradients to zero ...
            loss.zero_grad()
            # ... and delete the parts of the computation graph we don't need to remember.
            loss.clear()

        train_losses.append(cl/n)
        


        print(f'   running loss: {cl/n:.4}')
    
    return val_accuracies, train_losses, mlp



if __name__ == '__main__':
    
    
    # Parse command line arguments
    parser = ArgumentParser()

    parser.add_argument('-D', '--dataset',
                    dest='data',
                    help='Which dataset to use. [synth, mnist]',
                    default='synth', type=str)

    parser.add_argument('-b', '--batch-size',
                    dest='batch_size',
                    help='The batch size (how many instances to use for a single forward/backward pass).',
                    default=128, type=int)

    parser.add_argument('-e', '--epochs',
                    dest='epochs',
                    help='The number of epochs (complete passes over the complete training data).',
                    default=20, type=int)

    parser.add_argument('-l', '--learning-rate',
                    dest='lr',
                    help='The learning rate. That is, a scalar that determines the size of the steps taken by the '
                        'gradient descent algorithm. 0.1 works well for synth, 0.0001 works well for MNIST.',
                    default=0.01, type=float)

    args = parser.parse_args()




    ## Load the data
    if args.data == 'synth':
        (xtrain, ytrain), (xval, yval), num_classes = vg.load_synth()
    elif args.data == 'mnist':
        (xtrain, ytrain), (xval, yval), num_classes = vg.load_mnist(final=False, flatten=True)
    else:
        raise Exception(f'Dataset {args.data} not recognized.')

    print(f'## loaded data:')
    print(f'         number of instances: {xtrain.shape[0]} in training, {xval.shape[0]} in validation')
    print(f' training class distribution: {np.bincount(ytrain)}')
    print(f'     val. class distribution: {np.bincount(yval)}')

    num_instances, num_features = xtrain.shape
            

    ## Instantiate the model
    mlp = MLPReLU(input_size=num_features, output_size=num_classes)

    n, m = xtrain.shape
    b = args.batch_size

    print('\n## Starting training')
    for epoch in range(args.epochs):

        print(f'epoch {epoch:03}')

        ## Compute validation accuracy
        o = mlp(vg.TensorNode(xval))
        oval = o.value

        predictions = np.argmax(oval, axis=1)
        num_correct = (predictions == yval).sum()
        acc = num_correct / yval.shape[0]

        o.clear() # gc the computation graph
        print(f'       accuracy: {acc:.4}')

        cl = 0.0 # running sum of the training loss

        # We loop over the data in batches of size `b`
        for fr in range(0, n, b):

            # The end index of the batch
            to = min(fr + b, n)

            # Slice out the batch and its corresponding target values
            batch, targets = xtrain[fr:to, :], ytrain[fr:to]

            # Wrap the inputs in a Node
            batch = vg.TensorNode(value=batch)

            outputs = mlp(batch)
            loss = vg.logceloss(outputs, targets)
            # -- The computation graph is now complete. It consists of the MLP, together with the computation of
            #    the scalar loss.
            # -- The variable `loss` is the TensorNode at the very top of our computation graph. This means we can call
            #    it to perform operations on the computation graph, like clearing the gradients, starting the backpropgation
            #    and clearing the graph.
            # -- Note that we set the MLP up to produce log probabilties, so we should compute the CE loss for these.

            cl += loss.value
            # -- We must be careful here to extract the _raw_ value for the running loss. What would happen if we kept
            #    a running sum using the TensorNode?

            # Start the backpropagation
            loss.backward()

            # pply gradient descent
            for parm in mlp.parameters():
                parm.value -= args.lr * parm.grad
                # -- Note that we are directly manipulating the members of the parm TensorNode. This means that for this
                #    part, we are not building up a computation graph.

            # -- In Pytorch, the gradient descent is abstracted away into an Optimizer. This allows us to build slightly more
            #    complexoptimizers than plain graident descent.

            # Finally, we need to reset the gradients to zero ...
            loss.zero_grad()
            # ... and delete the parts of the computation graph we don't need to remember.
            loss.clear()

        print(f'   running loss: {cl/n:.4}')