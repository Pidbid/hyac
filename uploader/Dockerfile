# Use the official Node.js 18 image as a parent image
FROM node:20-alpine

# Install wget and then use the official pnpm install script
RUN npm install -g pnpm

# Set the working directory in the container
WORKDIR /app

# Copy package.json and install dependencies
COPY package.json .
RUN npm install

# Copy the uploader script
COPY uploader.js .

# Command to run the uploader. This will execute "node uploader.js"
CMD [ "node", "/app/uploader.js" ]
