/*
  ==============================================================================

	AsyncResizer.h
	Created: 8 Nov 2025 12:04:00am
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "AsyncUpdaterLambda.h"

class AsyncResizer : public AsyncUpdaterLambda {
public:
	AsyncResizer(Component* c) {
		onAsyncUpdate = [c]() {
			c->resized();
		};
	}

	void triggerAsyncResize() {
		triggerAsyncUpdate();
	}
};

