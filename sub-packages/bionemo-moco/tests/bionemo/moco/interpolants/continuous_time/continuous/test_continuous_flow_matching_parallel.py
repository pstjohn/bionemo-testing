# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-Apache2
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Optional

import pytest
import torch
import torch.multiprocessing.spawn
from torch.distributed.device_mesh import DeviceMesh

from bionemo.moco.distributions.prior.continuous.gaussian import GaussianPrior
from bionemo.moco.distributions.time.uniform import UniformTimeDistribution
from bionemo.moco.interpolants.continuous_time.continuous.continuous_flow_matching import ContinuousFlowMatcher
from bionemo.moco.testing.parallel_test_utils import parallel_context


@pytest.fixture
def flow_matcher():
    time_distribution = UniformTimeDistribution(discrete_time=False)
    prior = GaussianPrior(center=False)
    flow_matcher = ContinuousFlowMatcher(
        time_distribution=time_distribution, prior_distribution=prior, prediction_type="vector_field"
    )
    return flow_matcher


DEVICE_MESH: Optional[DeviceMesh] = None


def flow_matcher_parallel_interpolate(
    rank: int,
    flow_matcher,
    world_size: int = 1,
    device_type: str = "cuda",
):
    with parallel_context(rank=rank, world_size=world_size):
        data_gpu = torch.randint(0, 16, (5, 10)).to("cuda")
        t_gpu = flow_matcher.sample_time(5, device=data_gpu.device)
        noise_gpu = flow_matcher.sample_prior(data_gpu.shape, device=data_gpu.device)
        result = flow_matcher.interpolate(data_gpu, t_gpu, noise_gpu)
        # print(t_gpu, torch.distributed.get_rank())  # type: ignore
        assert result.shape == (5, 10)


@pytest.mark.parametrize("world_size", [1, 2])
def test_flow_matcher_parallel_interpolate(
    flow_matcher,
    world_size,
    device_type: str = "cuda",
):
    if not torch.cuda.is_available():
        pytest.skip("CUDA is not available")

    # Check if world_size number of devices are visible
    visible_devices = torch.cuda.device_count() if device_type == "cuda" else 1  # assume 1 for non-CUDA (e.g., CPU)
    if world_size > visible_devices:
        pytest.skip(f"Insufficient devices: {world_size} devices requested, but only {visible_devices} are visible")

    torch.multiprocessing.spawn(  # type: ignore
        fn=flow_matcher_parallel_interpolate,
        args=(
            flow_matcher,
            world_size,
            device_type,
        ),
        nprocs=world_size,
    )
