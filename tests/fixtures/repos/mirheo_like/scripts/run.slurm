#!/bin/bash
#SBATCH --nodes=2
srun ./simulate --gpu --mpi
