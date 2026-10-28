# Setting up Docker and Kubernetes on one machine

Cluster lessons run real multi-node clusters on **one** machine (your laptop or a single VM):

- **Docker Compose** lessons start several database containers (e.g. a 3-node cluster).
- **Kubernetes** lessons use **kind** ("Kubernetes in Docker"): each Kubernetes node is a Docker container, so one machine holds a whole cluster (1 control-plane + 3 workers). No extra VMs and no nested virtualization needed.

You install the tools once. Lessons create and delete their own clusters from `topics/<slug>/infra/`.

Without these tools, the cluster cells are skipped and show output recorded from a real run.

## Check what you have

```bash
python3 scripts/check_env.py            # Docker, kind, kubectl, helm, file-watch limits, CPU, RAM, disk
```

## Install (Ubuntu / Debian)

Versions current as of October 2026: kind v0.33.0, Helm 4. Check the linked pages for newer ones.

```bash
# 1. Docker  (https://docs.docker.com/engine/install/)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker      # run docker without sudo

# 2. kind  (https://kind.sigs.k8s.io/docs/user/quick-start/)
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.33.0/kind-linux-amd64   # use kind-linux-arm64 on ARM
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind

# 3. kubectl  (https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -m 0755 kubectl /usr/local/bin/kubectl && rm kubectl

# 4. Helm  (https://helm.sh/docs/intro/install/)
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
chmod 700 get_helm.sh && ./get_helm.sh && rm get_helm.sh

# 5. Raise file-watch limits; multi-node kind clusters need them
#    (https://kind.sigs.k8s.io/docs/user/known-issues/)
echo -e "fs.inotify.max_user_watches=524288\nfs.inotify.max_user_instances=512" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

On macOS or Windows: install Docker Desktop, then `brew install kind kubectl helm` (macOS) or `winget install Kubernetes.kind Kubernetes.kubectl Helm.Helm` (Windows). Give Docker Desktop at least 8 GB of memory in its settings.

## Quick test: a 4-node Kubernetes cluster

```bash
cat > kind-test.yaml <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
- role: worker
- role: worker
- role: worker
EOF
kind create cluster --name test --config kind-test.yaml
kubectl get nodes          # 4 nodes, all Ready
kind delete cluster --name test && rm kind-test.yaml
```

Or run `python3 scripts/check_env.py --smoke`, which does the same and cleans up.

## How big should the machine be?

Rough guide, not an official figure: **4+ CPUs, 16 GB RAM, 50 GB free disk** is comfortable. 8 GB of RAM can work if you run one cluster at a time with small replicas. Each lesson states the RAM it needs at the top.

## What one machine can't show you

All "nodes" share the same CPU, disk and network. Stopping a node container is a good stand-in for a node failing, but it doesn't reproduce real hardware, network or availability-zone failures, and speed numbers won't match a real cluster. Lessons say so in their "At real scale" sections and use published numbers for real-world scale.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `permission denied ... docker.sock` | `sudo usermod -aG docker $USER`, then log out and back in |
| `docker run hello-world` fails inside a "VM" | Some cloud dev environments are containers, not VMs, and can't run Docker; use a real VM |
| kind pods fail with "too many open files" | Step 5 above (file-watch limits) |
| kind cluster creation times out | Free memory (`free -h`), delete old clusters (`kind get clusters`, `kind delete cluster --name ...`) |
| Ports already in use | `docker ps` and stop old lesson containers; lessons document the ports they use |
