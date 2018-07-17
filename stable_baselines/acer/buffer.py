import numpy as np


class Buffer(object):
    def __init__(self, env, nsteps, nstack, size=50000):
        """
        A buffer for observations, actions, rewards, mu's, states, masks and dones values
        
        :param env: (Gym environment) The environment to learn from
        :param nsteps: (int) The number of steps to run for each environment
        :param nstack: (int) The number of stacked frames
        :param size: (int) The buffer size in number of steps
        """
        self.n_env = env.num_envs
        self.nsteps = nsteps
        self.height, self.width, self.n_channels = env.observation_space.shape
        self.nstack = nstack
        self.nbatch = self.n_env * self.nsteps
        # Each loc contains nenv * nsteps frames, thus total buffer is nenv * size frames
        self.size = size // self.nsteps

        # Memory
        self.enc_obs = None
        self.actions = None
        self.rewards = None
        self.mus = None
        self.dones = None
        self.masks = None

        # Size indexes
        self.next_idx = 0
        self.num_in_buffer = 0

    def has_atleast(self, frames):
        """
        Check to see if the buffer has at least the asked number of frames
        
        :param frames: (int) The number of frames checked
        :return: (bool) number of frames in buffer >= number asked
        """
        # Frames per env, so total (nenv * frames) Frames needed
        # Each buffer loc has nenv * nsteps frames
        return self.num_in_buffer >= (frames // self.nsteps)

    def can_sample(self):
        """
        Check if the buffer has at least one frame
        
        :return: (bool) if the buffer has at least one frame
        """
        return self.num_in_buffer > 0

    def decode(self, enc_obs, dones):
        """
        Get the stacked frames of an observation
        
        :param enc_obs: ([float]) the encoded observation
        :param dones: ([bool])
        :return: ([float]) the decoded observation
        """
        # enc_obs has shape [nenvs, nsteps + nstack, nh, nw, nc]
        # dones has shape [nenvs, nsteps, nh, nw, nc]
        # returns stacked obs of shape [nenv, (nsteps + 1), nh, nw, nstack*nc]
        n_stack, n_env, n_steps = self.nstack, self.n_env, self.nsteps
        height, width, n_channels = self.height, self.width, self.n_channels
        y_var = np.empty([n_steps + n_stack - 1, n_env, 1, 1, 1], dtype=np.float32)
        obs = np.zeros([n_stack, n_steps + n_stack, n_env, height, width, n_channels], dtype=np.uint8)
        # [nsteps + nstack, nenv, nh, nw, nc]
        x_var = np.reshape(enc_obs, [n_env, n_steps + n_stack, height, width, n_channels]).swapaxes(1, 0)
        y_var[3:] = np.reshape(1.0 - dones, [n_env, n_steps, 1, 1, 1]).swapaxes(1, 0)  # keep
        y_var[:3] = 1.0
        # y = np.reshape(1 - dones, [nenvs, nsteps, 1, 1, 1])
        for i in range(n_stack):
            obs[-(i + 1), i:] = x_var
            # obs[:,i:,:,:,-(i+1),:] = x
            x_var = x_var[:-1] * y_var
            y_var = y_var[1:]
        return np.reshape(obs[:, 3:].transpose((2, 1, 3, 4, 0, 5)),
                          [n_env, (n_steps + 1), height, width, n_stack * n_channels])

    def put(self, enc_obs, actions, rewards, mus, dones, masks):
        """
        Adds a frame to the buffer
        
        :param enc_obs: ([float]) the encoded observation
        :param actions: ([float]) the actions
        :param rewards: ([float]) the rewards
        :param mus: ([float]) the policy probability for the actions
        :param dones: ([bool])
        :param masks: ([bool])
        """
        # enc_obs [nenv, (nsteps + nstack), nh, nw, nc]
        # actions, rewards, dones [nenv, nsteps]
        # mus [nenv, nsteps, nact]

        if self.enc_obs is None:
            self.enc_obs = np.empty([self.size] + list(enc_obs.shape), dtype=np.uint8)
            self.actions = np.empty([self.size] + list(actions.shape), dtype=np.int32)
            self.rewards = np.empty([self.size] + list(rewards.shape), dtype=np.float32)
            self.mus = np.empty([self.size] + list(mus.shape), dtype=np.float32)
            self.dones = np.empty([self.size] + list(dones.shape), dtype=np.bool)
            self.masks = np.empty([self.size] + list(masks.shape), dtype=np.bool)

        self.enc_obs[self.next_idx] = enc_obs
        self.actions[self.next_idx] = actions
        self.rewards[self.next_idx] = rewards
        self.mus[self.next_idx] = mus
        self.dones[self.next_idx] = dones
        self.masks[self.next_idx] = masks

        self.next_idx = (self.next_idx + 1) % self.size
        self.num_in_buffer = min(self.size, self.num_in_buffer + 1)

    def take(self, arr, idx, envx):
        """
        Reads a frame from a list and index for the asked environment ids
        
        :param arr: (numpy array) the array that is read
        :param idx: ([int]) the idx that are read
        :param envx: ([int]) the idx for the environments
        :return: ([float]) the askes frames from the list
        """
        n_env = self.n_env
        out = np.empty([n_env] + list(arr.shape[2:]), dtype=arr.dtype)
        for i in range(n_env):
            out[i] = arr[idx[i], envx[i]]
        return out

    def get(self):
        """
        randomly read a frame from the buffer
        
        :return: ([float], [float], [float], [float], [bool], [float])
                 observations, actions, rewards, mus, dones, maskes
        """
        # returns
        # obs [nenv, (nsteps + 1), nh, nw, nstack*nc]
        # actions, rewards, dones [nenv, nsteps]
        # mus [nenv, nsteps, nact]
        n_env = self.n_env
        assert self.can_sample()

        # Sample exactly one id per env. If you sample across envs, then higher correlation in samples from same env.
        idx = np.random.randint(0, self.num_in_buffer, n_env)
        envx = np.arange(n_env)

        dones = self.take(self.dones, idx, envx)
        enc_obs = self.take(self.enc_obs, idx, envx)
        obs = self.decode(enc_obs, dones)
        actions = self.take(self.actions, idx, envx)
        rewards = self.take(self.rewards, idx, envx)
        mus = self.take(self.mus, idx, envx)
        masks = self.take(self.masks, idx, envx)
        return obs, actions, rewards, mus, dones, masks