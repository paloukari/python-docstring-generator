# Expose the port to ssh directly to the container
ufw allow 32001/tcp
# Mount the external disk
mkdir -m 777 /data
mkfs.ext4 /dev/xvdc
echo '/dev/xvdc /data                   ext4    defaults,noatime        0 0' >> /etc/fstab
mount /data

# Pull the code
cd /data
git clone --recurse-submodules https://github.com/paloukari/python-docstring-generator
cd /data/python-docstring-generator/

# Build the container
docker build \
    -t dev \
    -f Dockerfile.dev .

# Run the container
docker run \
    --rm \
    --runtime=nvidia \
     --name dev \
     -ti \
     --shm-size=1g \
     --ulimit memlock=-1 \
     --ulimit stack=67108864 \
     -v /data/python-docstring-generator:/data \
     -p 32001:22 dev